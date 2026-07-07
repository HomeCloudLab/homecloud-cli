"""Service APIs — thin facades over CoreContext."""

from __future__ import annotations

import json
from pathlib import Path
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
        body_str = body if isinstance(body, str) else json.dumps(body)
        payload: dict[str, Any] = {"body": body_str}
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

    def list_all_objects(
        self,
        bucket_name: str,
        *,
        prefix: str = "",
        recursive: bool = True,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            data = self.list_objects(
                bucket_name,
                prefix=prefix,
                recursive=recursive,
                page=page,
                page_size=100,
            )
            items.extend(
                item for item in data.get("items", []) if not item.get("is_dir")
            )
            if page >= int(data.get("pages", 1)):
                break
            page += 1
        return items

    def delete_recursive(self, bucket_name: str, prefix: str = "") -> int:
        deleted = 0
        for item in self.list_all_objects(bucket_name, prefix=prefix, recursive=True):
            self.delete(bucket_name, item["key"])
            deleted += 1
        return deleted

    def sync_local_to_bucket(
        self,
        local_dir: str | Path,
        bucket_name: str,
        *,
        prefix: str = "",
        delete: bool = False,
    ) -> dict[str, int]:
        """Upload local directory to bucket (one-way, like aws s3 sync local → remote)."""
        root = Path(local_dir)
        if not root.is_dir():
            raise HomeCloudError(f"Not a directory: {local_dir}")

        prefix_clean = prefix.strip("/")
        local_files: dict[str, Path] = {}
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            key = f"{prefix_clean}/{rel}" if prefix_clean else rel
            local_files[key] = path

        remote_items = self.list_all_objects(
            bucket_name,
            prefix=prefix_clean,
            recursive=True,
        )
        remote_by_key = {item["key"]: item for item in remote_items}

        uploaded = 0
        skipped = 0
        for key, path in sorted(local_files.items()):
            remote = remote_by_key.get(key)
            local_size = path.stat().st_size
            if remote is not None and remote.get("size") == local_size:
                skipped += 1
                continue
            self.upload(bucket_name, path.as_posix(), key=key)
            uploaded += 1

        deleted = 0
        if delete:
            for key in remote_by_key:
                if key not in local_files:
                    self.delete(bucket_name, key)
                    deleted += 1

        return {"uploaded": uploaded, "skipped": skipped, "deleted": deleted}


class SecretsAPI:
    def __init__(self, ctx: CoreContext) -> None:
        self._ctx = ctx

    def list(self) -> list[dict[str, Any]]:
        account_id = self._ctx.account_id()
        data = self._ctx.transport.console_request("GET", f"accounts/{account_id}/secrets")
        return data.get("items", [])
