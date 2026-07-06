"""Temporary session state — JWT and active account selection."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from homecloud_core.config import homecloud_dir


def session_path() -> Path:
    override = os.environ.get("HOMECLOUD_SESSION_FILE")
    if override:
        return Path(override).expanduser()
    return homecloud_dir() / "session"


@dataclass
class ProfileSession:
    access_token: str | None = None
    active_account_id: str | None = None
    last_used_account_id: str | None = None


@dataclass
class SessionFile:
    version: int
    profiles: dict[str, ProfileSession]

    def get(self, profile_name: str) -> ProfileSession:
        return self.profiles.setdefault(profile_name, ProfileSession())


def load_session(path: Path | None = None) -> SessionFile:
    session_file = path or session_path()
    if not session_file.exists():
        return SessionFile(version=1, profiles={})

    raw = json.loads(session_file.read_text(encoding="utf-8"))
    profiles = {
        name: ProfileSession(
            access_token=data.get("access_token"),
            active_account_id=data.get("active_account_id"),
            last_used_account_id=data.get("last_used_account_id"),
        )
        for name, data in raw.get("profiles", {}).items()
    }
    return SessionFile(version=int(raw.get("version", 1)), profiles=profiles)


def save_session(session: SessionFile, path: Path | None = None) -> Path:
    session_file = path or session_path()
    session_file.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "version": session.version,
        "profiles": {
            name: {
                **({"access_token": profile.access_token} if profile.access_token else {}),
                **({"active_account_id": profile.active_account_id} if profile.active_account_id else {}),
                **(
                    {"last_used_account_id": profile.last_used_account_id}
                    if profile.last_used_account_id
                    else {}
                ),
            }
            for name, profile in session.profiles.items()
            if profile.access_token or profile.active_account_id or profile.last_used_account_id
        },
    }

    session_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        session_file.chmod(0o600)
    except OSError:
        pass
    return session_file


def set_access_token(profile_name: str, token: str) -> Path:
    session = load_session()
    profile_session = session.get(profile_name)
    profile_session.access_token = token
    session.profiles[profile_name] = profile_session
    return save_session(session)


def set_active_account(profile_name: str, account_id: str) -> Path:
    session = load_session()
    profile_session = session.get(profile_name)
    profile_session.active_account_id = account_id
    profile_session.last_used_account_id = account_id
    session.profiles[profile_name] = profile_session
    return save_session(session)


def get_access_token(profile_name: str) -> str | None:
    return load_session().get(profile_name).access_token


def migrate_legacy_token_from_credentials(
    profile_name: str,
    access_token: str | None,
) -> None:
    if not access_token:
        return
    session = load_session()
    profile_session = session.get(profile_name)
    if not profile_session.access_token:
        profile_session.access_token = access_token
        session.profiles[profile_name] = profile_session
        save_session(session)
