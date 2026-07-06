"""Runtime context — wires credentials, session, transport, and account resolution."""

from __future__ import annotations

import os
from typing import Any

from homecloud_core.account import remember_account, resolve_account_id
from homecloud_core.config import (
    ProfileConfig,
    load_credentials,
    upsert_profile,
)
from homecloud_core.defaults import DEFAULT_PROFILE, platform_apex
from homecloud_core.errors import HomeCloudError
from homecloud_core.session import (
    get_access_token,
    load_session,
    migrate_legacy_token_from_credentials,
    set_access_token,
)
from homecloud_core.transport import Transport


class CoreContext:
    def __init__(self, profile_name: str | None = None) -> None:
        self.profile_name = profile_name or os.environ.get("HOMECLOUD_PROFILE", DEFAULT_PROFILE)
        try:
            credentials = load_credentials()
            self.profile = credentials.get_profile(self.profile_name)
        except FileNotFoundError:
            self.profile = ProfileConfig(name=self.profile_name)
        self._session = load_session().get(self.profile_name)
        self._apply_env_overrides()
        self._transport = Transport(
            apex=self.profile.apex,
            access_key_id=self.profile.access_key_id,
            secret_access_key=self.profile.secret_access_key,
            access_token=self._session.access_token,
        )

    def _apply_env_overrides(self) -> None:
        if account := os.environ.get("HOMECLOUD_ACCOUNT_ID"):
            self.profile.default_account_id = account
        if key_id := os.environ.get("HOMECLOUD_ACCESS_KEY_ID"):
            self.profile.access_key_id = key_id
        if secret := os.environ.get("HOMECLOUD_SECRET_ACCESS_KEY"):
            self.profile.secret_access_key = secret

    @property
    def transport(self) -> Transport:
        return self._transport

    def account_id(self) -> str:
        account_id = resolve_account_id(self.profile, self._session)
        remember_account(self.profile_name, account_id)
        return account_id

    def login(self, email: str, password: str) -> None:
        data = self._transport.console_request(
            "POST",
            "auth/login",
            json={"email": email, "password": password},
            require_auth=False,
        )
        token = data.get("access_token")
        if not token:
            raise HomeCloudError("Login failed")
        set_access_token(self.profile_name, token)
        self._transport.access_token = token
        self._session = load_session().get(self.profile_name)
        self._auto_select_account()

    def _auto_select_account(self) -> None:
        if self._session.active_account_id or self.profile.default_account_id:
            return
        accounts = self.list_accounts()
        if len(accounts) == 1:
            remember_account(self.profile_name, str(accounts[0]["id"]))

    def list_accounts(self) -> list[dict[str, Any]]:
        data = self._transport.console_request("GET", "accounts")
        return data.get("items", data if isinstance(data, list) else [])

    def switch_account(self, account_ref: str) -> None:
        accounts = self.list_accounts()
        match = next(
            (
                account
                for account in accounts
                if str(account.get("id")) == account_ref
                or str(account.get("slug")) == account_ref
                or str(account.get("name")) == account_ref
            ),
            None,
        )
        if not match:
            raise HomeCloudError(f"Account not found: {account_ref}")
        remember_account(self.profile_name, str(match["id"]))

    @staticmethod
    def configure_profile(
        *,
        profile_name: str,
        access_key_id: str,
        secret_access_key: str,
        default_account_id: str | None = None,
        apex: str | None = None,
        make_default: bool = True,
    ) -> None:
        upsert_profile(
            ProfileConfig(
                name=profile_name,
                apex=apex or platform_apex(),
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                default_account_id=default_account_id,
            ),
            make_default=make_default,
        )

    @staticmethod
    def import_credentials_file(
        raw: dict[str, Any],
        *,
        profile_name: str = DEFAULT_PROFILE,
    ) -> None:
        migrate_legacy_token_from_credentials(profile_name, raw.get("access_token"))
        CoreContext.configure_profile(
            profile_name=profile_name,
            access_key_id=raw["access_key_id"],
            secret_access_key=raw["secret_access_key"],
            default_account_id=raw.get("default_account_id"),
            apex=raw.get("apex"),
        )

    def config_summary(self) -> dict[str, Any]:
        from homecloud_core.config import credentials_path, load_credentials, mask_secret
        from homecloud_core.session import session_path

        try:
            load_credentials()
            configured = True
        except FileNotFoundError:
            configured = False

        return {
            "profile": self.profile_name,
            "apex": self.profile.apex,
            "credentials_file": str(credentials_path()),
            "session_file": str(session_path()),
            "configured": configured,
            "access_key_id": self.profile.access_key_id,
            "secret_access_key": mask_secret(self.profile.secret_access_key),
            "logged_in": bool(get_access_token(self.profile_name)),
            "has_account": bool(
                self._session.active_account_id or self.profile.default_account_id
            ),
        }
