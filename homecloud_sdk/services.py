"""Service APIs — thin facades over CoreContext."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from homecloud_core.context import CoreContext
from homecloud_core.errors import HomeCloudError
from homecloud_sdk.so_parallel import DEFAULT_SO_WORKERS, run_parallel


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


class SoAPI:
    """Object storage (SO) — use client.so, not client.storage."""

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

    def download(
        self,
        bucket_name: str,
        object_key: str,
        *,
        dest_path: str | Path,
    ) -> dict[str, Any]:
        account_id = self._ctx.account_id()
        key = object_key.lstrip("/")
        path = f"/{account_id}/{bucket_name}/objects/{key}"
        content = self._ctx.transport.data_plane_request_bytes("so", "GET", path, account_id)
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return {"key": key, "size": len(content), "path": str(dest)}

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

    def delete_recursive(
        self,
        bucket_name: str,
        prefix: str = "",
        *,
        max_workers: int = DEFAULT_SO_WORKERS,
        on_begin: Callable[[int], None] | None = None,
        on_delete: Callable[[str], None] | None = None,
    ) -> int:
        items = self.list_all_objects(bucket_name, prefix=prefix, recursive=True)
        if on_begin is not None:
            on_begin(len(items))
        keys = [item["key"] for item in items]

        def do_delete(key: str) -> None:
            self.delete(bucket_name, key)
            if on_delete is not None:
                on_delete(key)

        run_parallel(keys, do_delete, max_workers=max_workers)
        return len(keys)

    def sync_local_to_bucket(
        self,
        local_dir: str | Path,
        bucket_name: str,
        *,
        prefix: str = "",
        delete: bool = False,
        skip: bool = False,
        max_workers: int = DEFAULT_SO_WORKERS,
        on_upload: Callable[[str], None] | None = None,
        on_skip: Callable[[str], None] | None = None,
        on_delete: Callable[[str], None] | None = None,
        on_begin: Callable[[int], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> dict[str, int]:
        """Upload local directory to bucket (one-way). Overwrites by default; use skip=True to skip same-size keys."""
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

        to_upload: list[str] = []
        to_skip: list[str] = []
        for key, path in sorted(local_files.items()):
            remote = remote_by_key.get(key)
            local_size = path.stat().st_size
            if skip and remote is not None and remote.get("size") == local_size:
                to_skip.append(key)
            else:
                to_upload.append(key)

        to_delete = (
            [key for key in remote_by_key if key not in local_files]
            if delete
            else []
        )

        total_ops = len(to_upload) + len(to_skip) + len(to_delete)
        if on_status is not None:
            on_status(f"scan  {len(local_files)} local, {len(remote_by_key)} remote, {total_ops} operations")
        if on_begin is not None:
            on_begin(total_ops)

        skipped = 0
        for key in to_skip:
            if on_skip is not None:
                on_skip(key)
            skipped += 1

        def do_upload(key: str) -> None:
            path = local_files[key]
            self.upload(bucket_name, path.as_posix(), key=key)
            if on_upload is not None:
                on_upload(key)

        run_parallel(to_upload, do_upload, max_workers=max_workers)
        uploaded = len(to_upload)

        deleted = 0

        def do_delete(key: str) -> None:
            self.delete(bucket_name, key)
            if on_delete is not None:
                on_delete(key)

        run_parallel(to_delete, do_delete, max_workers=max_workers)
        deleted = len(to_delete)

        return {"uploaded": uploaded, "skipped": skipped, "deleted": deleted}

    def sync_bucket_to_local(
        self,
        bucket_name: str,
        local_dir: str | Path,
        *,
        prefix: str = "",
        delete: bool = False,
        skip: bool = False,
        max_workers: int = DEFAULT_SO_WORKERS,
        on_download: Callable[[str], None] | None = None,
        on_skip: Callable[[str], None] | None = None,
        on_delete: Callable[[str], None] | None = None,
        on_begin: Callable[[int], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> dict[str, int]:
        """Download bucket prefix to local directory. Overwrites by default; use skip=True to skip same-size files."""
        root = Path(local_dir)
        root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir():
            raise HomeCloudError(f"Not a directory: {local_dir}")

        prefix_clean = prefix.strip("/")
        remote_items = self.list_all_objects(
            bucket_name,
            prefix=prefix_clean,
            recursive=True,
        )
        remote_by_key = {item["key"]: item for item in remote_items}

        local_files: dict[str, Path] = {}
        if root.exists():
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                key = f"{prefix_clean}/{rel}" if prefix_clean else rel
                local_files[key] = path

        to_download: list[str] = []
        to_skip: list[str] = []
        for key in sorted(remote_by_key):
            remote = remote_by_key[key]
            local_path = local_files.get(key)
            remote_size = int(remote.get("size") or 0)
            if (
                skip
                and local_path is not None
                and local_path.is_file()
                and local_path.stat().st_size == remote_size
            ):
                to_skip.append(key)
            else:
                to_download.append(key)

        to_delete = (
            [key for key in local_files if key not in remote_by_key]
            if delete
            else []
        )

        total_ops = len(to_download) + len(to_skip) + len(to_delete)
        if on_status is not None:
            on_status(
                f"scan  {len(remote_by_key)} remote, {len(local_files)} local, {total_ops} operations"
            )
        if on_begin is not None:
            on_begin(total_ops)

        skipped = 0
        for key in to_skip:
            if on_skip is not None:
                on_skip(key)
            skipped += 1

        def do_download(key: str) -> None:
            rel = key[len(prefix_clean) + 1 :] if prefix_clean else key
            dest = root / rel
            self.download(bucket_name, key, dest_path=dest)
            local_files[key] = dest
            if on_download is not None:
                on_download(key)

        run_parallel(to_download, do_download, max_workers=max_workers)
        downloaded = len(to_download)

        deleted = 0
        for key in to_delete:
            path = local_files[key]
            if path.is_file():
                path.unlink()
            if on_delete is not None:
                on_delete(key)
            deleted += 1

        return {"downloaded": downloaded, "skipped": skipped, "deleted": deleted}


StorageAPI = SoAPI


class SecretsAPI:
    def __init__(self, ctx: CoreContext) -> None:
        self._ctx = ctx

    def list(self) -> list[dict[str, Any]]:
        account_id = self._ctx.account_id()
        data = self._ctx.transport.console_request("GET", f"accounts/{account_id}/secrets")
        return data.get("items", [])
