"""Single public entry point for CLI and SDK consumers."""

from __future__ import annotations

from typing import Any

from homecloud_core.context import CoreContext
from homecloud_sdk.services import AccountsAPI, AppsAPI, MqAPI, QueuesAPI, SecretsAPI, StorageAPI


class HomeCloudClient:
    """AWS-style client — no auth, account, or endpoint parameters."""

    def __init__(self, profile: str | None = None) -> None:
        self._ctx = CoreContext(profile)

    @classmethod
    def from_profile(cls, profile: str) -> HomeCloudClient:
        return cls(profile=profile)

    @property
    def accounts(self) -> AccountsAPI:
        return AccountsAPI(self._ctx)

    @property
    def apps(self) -> AppsAPI:
        return AppsAPI(self._ctx)

    @property
    def queues(self) -> QueuesAPI:
        return QueuesAPI(self._ctx)

    @property
    def mq(self) -> MqAPI:
        return MqAPI(self._ctx)

    @property
    def storage(self) -> StorageAPI:
        return StorageAPI(self._ctx)

    @property
    def secrets(self) -> SecretsAPI:
        return SecretsAPI(self._ctx)

    def login(self, email: str, password: str) -> None:
        self._ctx.login(email, password)

    def configure(
        self,
        *,
        access_key_id: str,
        secret_access_key: str,
        default_account_id: str | None = None,
    ) -> None:
        CoreContext.configure_profile(
            profile_name=self._ctx.profile_name,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            default_account_id=default_account_id,
        )

    def import_credentials(self, raw: dict[str, Any]) -> None:
        CoreContext.import_credentials_file(raw, profile_name=self._ctx.profile_name)

    def config_summary(self) -> dict[str, Any]:
        return self._ctx.config_summary()
