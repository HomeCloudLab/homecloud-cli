"""Automatic account resolution — users never pass account IDs."""

from __future__ import annotations

from homecloud_core.config import ProfileConfig
from homecloud_core.errors import NotConfiguredError
from homecloud_core.session import ProfileSession, set_active_account


def resolve_account_id(profile: ProfileConfig, session: ProfileSession) -> str:
    if session.active_account_id:
        return session.active_account_id
    if profile.default_account_id:
        return profile.default_account_id
    if session.last_used_account_id:
        return session.last_used_account_id
    raise NotConfiguredError(
        "No active account for this profile. Run: homecloud configure or homecloud accounts switch"
    )


def remember_account(profile_name: str, account_id: str) -> None:
    set_active_account(profile_name, account_id)
