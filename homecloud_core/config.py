"""Persistent credentials — Access Keys only, no session tokens."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from homecloud_core.defaults import DEFAULT_PROFILE, platform_apex


def homecloud_dir() -> Path:
    override = os.environ.get("HOMECLOUD_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".homecloud"


def credentials_path() -> Path:
    override = os.environ.get("HOMECLOUD_CREDENTIALS_FILE")
    if override:
        return Path(override).expanduser()
    return homecloud_dir() / "credentials"


@dataclass
class ProfileConfig:
    name: str
    apex: str = platform_apex()
    default_account_id: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None

    def require_access_key(self) -> tuple[str, str, str]:
        if not self.default_account_id:
            raise ValueError("No account configured for this profile. Run: homecloud configure")
        if not self.access_key_id or not self.secret_access_key:
            raise ValueError("Access Key not configured. Run: homecloud configure")
        return self.default_account_id, self.access_key_id, self.secret_access_key


@dataclass
class CredentialsFile:
    version: int
    default_profile: str
    profiles: dict[str, ProfileConfig]

    def get_profile(self, name: str | None = None) -> ProfileConfig:
        profile_name = name or self.default_profile
        if profile_name not in self.profiles:
            raise ValueError(f"Profile not found: {profile_name}")
        return self.profiles[profile_name]


def _profile_from_dict(name: str, data: dict[str, Any]) -> ProfileConfig:
    return ProfileConfig(
        name=name,
        apex=data.get("apex", platform_apex()),
        default_account_id=data.get("default_account_id"),
        access_key_id=data.get("access_key_id"),
        secret_access_key=data.get("secret_access_key"),
    )


def _strip_legacy_session_fields(data: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(data)
    cleaned.pop("access_token", None)
    cleaned.pop("console_url", None)
    cleaned.pop("mq_url", None)
    cleaned.pop("so_url", None)
    cleaned.pop("secrets_url", None)
    return cleaned


def _normalize_raw(data: dict[str, Any]) -> dict[str, Any]:
    if "profiles" in data:
        return {
            "version": data.get("version", 2),
            "default_profile": data.get("default_profile", DEFAULT_PROFILE),
            "profiles": {
                name: _strip_legacy_session_fields(profile_data)
                for name, profile_data in data["profiles"].items()
            },
        }

    profile = _strip_legacy_session_fields(data)
    return {
        "version": data.get("version", 2),
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
        version=int(normalized.get("version", 2)),
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
                "apex": profile.apex,
                "default_account_id": profile.default_account_id,
                "access_key_id": profile.access_key_id,
                "secret_access_key": profile.secret_access_key,
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


def upsert_profile(profile: ProfileConfig, *, make_default: bool = True) -> Path:
    try:
        credentials = load_credentials()
    except FileNotFoundError:
        credentials = CredentialsFile(version=2, default_profile=profile.name, profiles={})

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
