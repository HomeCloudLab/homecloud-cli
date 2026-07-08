"""SO object path helpers — canonical sign path vs URL-encoded request path."""

from __future__ import annotations

from urllib.parse import quote


def encode_object_key_path(key: str) -> str:
    """Encode each object key segment for the HTTP path (spaces → %20, etc.)."""
    return "/".join(quote(part, safe="") for part in key.lstrip("/").split("/"))


def so_object_paths(account_id: str, bucket_name: str, object_key: str) -> tuple[str, str]:
    """Return (sign_path, url_path) for object GET/DELETE."""
    key = object_key.lstrip("/")
    sign_path = f"/{account_id}/{bucket_name}/objects/{key}"
    url_path = f"/{account_id}/{bucket_name}/objects/{encode_object_key_path(key)}"
    return sign_path, url_path


def sync_relative_local_path(key: str, prefix_clean: str) -> str:
    """Map remote object key to a relative path under the sync destination directory."""
    if not prefix_clean:
        return key
    if key == prefix_clean:
        return key.rsplit("/", 1)[-1]
    if key.startswith(f"{prefix_clean}/"):
        return key[len(prefix_clean) + 1 :]
    return key
