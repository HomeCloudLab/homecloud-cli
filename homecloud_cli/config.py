"""Load and save ~/.homecloud/credentials with multi-profile support."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONSOLE_URL = "https://console.holab.abrdns.com/api/v1"
DEFAULT_MQ_URL = "https://mq.holab.abrdns.com"
DEFAULT_SO_URL = "https://so.holab.abrdns.com"
DEFAULT_SECRETS_URL = "https://secrets.holab.abrdns.com"
DEFAULT_PROFILE = "default"


def credentials_path() -> Path:
    override = os.environ.get("HOMECLOUD_CREDENTIALS_FILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".homecloud" / "credentials"


@dataclass
class Profile:
    name: str
    console_url: str = DEFAULT_CONSOLE_URL
    mq_url: str = DEFAULT_MQ_URL
    so_url: str = DEFAULT_SO_URL
    secrets_url: str = DEFAULT_SECRETS_URL
    default_account_id: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    access_token: str | None = None

    def require_access_key(self) -> tuple[str, str, str]:
        if not self.default_account_id:
            raise ValueError("default_account_id is not configured")
        if not self.access_key_id or not self.secret_access_key:
            raise ValueError("access_key_id and secret_access_key are required")
        return self.default_account_id, self.access_key_id, self.secret_access_key

    def require_console_token(self) -> str:
        if not self.access_token:
            raise ValueError("Not logged in. Run: homecloud login")
        return self.access_token


@dataclass
class CredentialsFile:
    version: int
    default_profile: str
    profiles: dict[str, Profile]

    def get_profile(self, name: str | None = None) -> Profile:
        profile_name = name or self.default_profile
        if profile_name not in self.profiles:
            raise ValueError(f"Profile not found: {profile_name}")
        return self.profiles[profile_name]


def _profile_from_dict(name: str, data: dict[str, Any]) -> Profile:
    return Profile(
        name=name,
        console_url=data.get("console_url", DEFAULT_CONSOLE_URL),
        mq_url=data.get("mq_url", DEFAULT_MQ_URL),
        so_url=data.get("so_url", DEFAULT_SO_URL),
        secrets_url=data.get("secrets_url", DEFAULT_SECRETS_URL),
        default_account_id=data.get("default_account_id"),
        access_key_id=data.get("access_key_id"),
        secret_access_key=data.get("secret_access_key"),
        access_token=data.get("access_token"),
    )


def _normalize_raw(data: dict[str, Any]) -> dict[str, Any]:
    """Accept flat UI export format and upgrade to multi-profile layout."""
    if "profiles" in data:
        return data

    profile = {
        "console_url": data.get("console_url", DEFAULT_CONSOLE_URL),
        "mq_url": data.get("mq_url", DEFAULT_MQ_URL),
        "so_url": data.get("so_url", DEFAULT_SO_URL),
        "secrets_url": data.get("secrets_url", DEFAULT_SECRETS_URL),
        "default_account_id": data.get("default_account_id"),
        "access_key_id": data.get("access_key_id"),
        "secret_access_key": data.get("secret_access_key"),
        "access_token": data.get("access_token"),
    }
    return {
        "version": data.get("version", 1),
        "default_profile": data.get("default_profile", DEFAULT_PROFILE),
        "profiles": {DEFAULT_PROFILE: profile},
    }


def load_credentials(path: Path | None = None) -> CredentialsFile:
    cred_path = path or credentials_path()
    if not cred_path.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {cred_path}. Run: homecloud configure"
        )

    raw = json.loads(cred_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Invalid credentials file: expected JSON object")

    normalized = _normalize_raw(raw)
    profiles = {
        name: _profile_from_dict(name, profile_data)
        for name, profile_data in normalized.get("profiles", {}).items()
    }
    if not profiles:
        raise ValueError("No profiles found in credentials file")

    return CredentialsFile(
        version=int(normalized.get("version", 1)),
        default_profile=normalized.get("default_profile", DEFAULT_PROFILE),
        profiles=profiles,
    )


def save_credentials(credentials: CredentialsFile, path: Path | None = None) -> Path:
    cred_path = path or credentials_path()
    cred_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": credentials.version,
        "default_profile": credentials.default_profile,
        "profiles": {
            name: {
                "console_url": profile.console_url,
                "mq_url": profile.mq_url,
                "so_url": profile.so_url,
                "secrets_url": profile.secrets_url,
                "default_account_id": profile.default_account_id,
                "access_key_id": profile.access_key_id,
                "secret_access_key": profile.secret_access_key,
                **({"access_token": profile.access_token} if profile.access_token else {}),
            }
            for name, profile in credentials.profiles.items()
        },
    }

    cred_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        cred_path.chmod(0o600)
    except OSError:
        pass
    return cred_path


def upsert_profile(profile: Profile, *, make_default: bool = True) -> Path:
    try:
        credentials = load_credentials()
    except FileNotFoundError:
        credentials = CredentialsFile(version=1, default_profile=profile.name, profiles={})

    credentials.profiles[profile.name] = profile
    if make_default:
        credentials.default_profile = profile.name
    return save_credentials(credentials)


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"
