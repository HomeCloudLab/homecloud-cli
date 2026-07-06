"""Service APIs — thin facades over CoreContext."""

from __future__ import annotations

from typing import Any

from homecloud_core.context import CoreContext
from homecloud_core.errors import HomeCloudError


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

    def list_objects(
        self,
        bucket_name: str,
        *,
        prefix: str = "",
        recursive: bool = False,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        account_id = self._ctx.account_id()
        path = f"/{account_id}/{bucket_name}/objects"
        return self._ctx.transport.data_plane_request(
            "so",
            "GET",
            path,
            account_id,
            params={
                "prefix": prefix,
                "recursive": recursive,
                "page": page,
                "page_size": page_size,
            },
        )

    def upload(
        self,
        bucket_name: str,
        file_path: str,
        *,
        key: str | None = None,
    ) -> dict[str, Any]:
        from pathlib import Path

        path = Path(file_path)
        if not path.is_file():
            raise HomeCloudError(f"File not found: {file_path}")

        object_key = key or path.name
        account_id = self._ctx.account_id()
        upload_path = f"/{account_id}/{bucket_name}/objects"
        with path.open("rb") as handle:
            return self._ctx.transport.data_plane_request(
                "so",
                "POST",
                upload_path,
                account_id,
                data={"key": object_key},
                files={"file": (path.name, handle, "application/octet-stream")},
            )

    def delete(self, bucket_name: str, object_key: str) -> None:
        account_id = self._ctx.account_id()
        path = f"/{account_id}/{bucket_name}/objects/{object_key.lstrip('/')}"
        self._ctx.transport.data_plane_request("so", "DELETE", path, account_id)


class SecretsAPI:
    def __init__(self, ctx: CoreContext) -> None:
        self._ctx = ctx

    def list(self) -> list[dict[str, Any]]:
        account_id = self._ctx.account_id()
        data = self._ctx.transport.console_request("GET", f"accounts/{account_id}/secrets")
        return data.get("items", [])
