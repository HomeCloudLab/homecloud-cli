"""Service APIs — thin facades over CoreContext."""

from __future__ import annotations

from typing import Any

from homecloud_core.context import CoreContext


class AccountsAPI:
    def __init__(self, ctx: CoreContext) -> None:
        self._ctx = ctx

    def list(self) -> list[dict[str, Any]]:
        return self._ctx.list_accounts()

    def switch(self, account_ref: str) -> None:
        self._ctx.switch_account(account_ref)


class QueuesAPI:
    def __init__(self, ctx: CoreContext) -> None:
        self._ctx = ctx

    def list(self) -> list[dict[str, Any]]:
        account_id = self._ctx.account_id()
        data = self._ctx.transport.console_request("GET", f"accounts/{account_id}/queues")
        return data.get("items", [])


class MqAPI:
    def __init__(self, ctx: CoreContext) -> None:
        self._ctx = ctx

    def send(
        self,
        queue_name: str,
        body: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        account_id = self._ctx.account_id()
        path = f"/{account_id}/{queue_name}/messages"
        payload: dict[str, Any] = {"body": body}
        if headers:
            payload["headers"] = headers
        return self._ctx.transport.data_plane_request(
            "mq",
            "POST",
            path,
            account_id,
            json=payload,
        )

    def receive(
        self,
        queue_name: str,
        *,
        max_messages: int = 1,
        wait_seconds: int = 20,
    ) -> list[dict[str, Any]]:
        account_id = self._ctx.account_id()
        path = f"/{account_id}/{queue_name}/messages"
        data = self._ctx.transport.data_plane_request(
            "mq",
            "GET",
            path,
            account_id,
            params={"max_messages": max_messages, "wait_seconds": wait_seconds},
        )
        return data.get("items", [])


class AppsAPI:
    def __init__(self, ctx: CoreContext) -> None:
        self._ctx = ctx

    def list(self) -> list[dict[str, Any]]:
        account_id = self._ctx.account_id()
        data = self._ctx.transport.console_request("GET", f"accounts/{account_id}/applications")
        return data.get("items", [])


class StorageAPI:
    def __init__(self, ctx: CoreContext) -> None:
        self._ctx = ctx

    def list_buckets(self) -> list[dict[str, Any]]:
        account_id = self._ctx.account_id()
        data = self._ctx.transport.console_request("GET", f"accounts/{account_id}/storage/buckets")
        return data.get("items", [])


class SecretsAPI:
    def __init__(self, ctx: CoreContext) -> None:
        self._ctx = ctx

    def list(self) -> list[dict[str, Any]]:
        account_id = self._ctx.account_id()
        data = self._ctx.transport.console_request("GET", f"accounts/{account_id}/secrets")
        return data.get("items", [])
