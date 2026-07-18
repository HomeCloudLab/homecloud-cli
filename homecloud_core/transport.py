"""Unified HTTP transport — auth and routing are internal."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

import httpx

from homecloud_core.defaults import WHOAMI_ACCOUNT_SENTINEL, WHOAMI_PATH, console_url, mq_url, secrets_url, so_url
from homecloud_core.errors import HomeCloudError, NotLoggedInError
from homecloud_core.signing import sign_request_headers

Plane = Literal["console", "mq", "so", "secrets"]

_MAX_RETRIES = 2
_RETRY_STATUS = {502, 503, 504}


class Transport:
    def __init__(
        self,
        *,
        apex: str,
        access_key_id: str | None,
        secret_access_key: str | None,
        access_token: str | None,
        timeout: float = 30.0,
        mfa_resolver: Any | None = None,
    ) -> None:
        self.apex = apex
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.access_token = access_token
        self.timeout = timeout
        self._mfa_resolver = mfa_resolver
        self._http_client: httpx.Client | None = None
        self._http_lock = threading.Lock()

    def set_mfa_resolver(self, resolver: Any | None) -> None:
        self._mfa_resolver = resolver

    def _http(self) -> httpx.Client:
        with self._http_lock:
            if self._http_client is None:
                self._http_client = httpx.Client(
                    timeout=httpx.Timeout(self.timeout),
                    limits=httpx.Limits(max_connections=100, max_keepalive_connections=32),
                )
            return self._http_client

    def close(self) -> None:
        with self._http_lock:
            if self._http_client is not None:
                self._http_client.close()
                self._http_client = None

    def console_request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        require_auth: bool = True,
        _skip_mfa: bool = False,
    ) -> Any:
        if require_auth and not self.access_token:
            raise NotLoggedInError("Not logged in. Run: homecloud login")

        headers: dict[str, str] = {}
        if require_auth and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        url = urljoin(console_url(self.apex).rstrip("/") + "/", path.lstrip("/"))
        try:
            return self._request(method, url, headers=headers, json=json, params=params)
        except HomeCloudError as exc:
            if _skip_mfa or self._mfa_resolver is None:
                raise
            from homecloud_core.mfa import is_mfa_required

            if not is_mfa_required(exc):
                raise

            def retry(
                retry_method: str,
                retry_path: str,
                *,
                json: Any | None = None,
                require_auth: bool = True,
                _skip_mfa: bool = True,
                **_kwargs: Any,
            ) -> Any:
                return self.console_request(
                    retry_method,
                    retry_path,
                    json=json,
                    params=params,
                    require_auth=require_auth,
                    _skip_mfa=_skip_mfa,
                )

            return self._mfa_resolver.resolve(
                exc,
                method=method,
                path=path,
                json_body=json,
                retry=retry,
            )

    def data_plane_request_bytes(
        self,
        plane: Plane,
        method: str,
        path: str,
        account_id: str,
        *,
        url_path: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> bytes:
        """Raw response body for binary endpoints (e.g. SO object download)."""
        if not self.access_key_id or not self.secret_access_key:
            raise HomeCloudError(
                "Access Key not configured. "
                "Run: homecloud configure, or pass --access-key-id and --secret-access-key"
            )

        base_urls = {
            "mq": mq_url(self.apex),
            "so": so_url(self.apex),
            "secrets": secrets_url(self.apex),
        }
        headers = sign_request_headers(
            access_key_id=self.access_key_id,
            secret=self.secret_access_key,
            method=method,
            path=path,
            account_id=account_id,
        )
        url = f"{base_urls[plane].rstrip('/')}{url_path or path}"
        last_error: HomeCloudError | None = None
        client = self._http()
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = client.request(method, url, headers=headers, params=params)
            except httpx.HTTPError as exc:
                if attempt == _MAX_RETRIES:
                    raise HomeCloudError(f"Request failed: {exc}") from exc
                time.sleep(0.5 * (attempt + 1))
                continue
            if response.status_code not in _RETRY_STATUS or attempt == _MAX_RETRIES:
                if response.is_success:
                    return response.content
                detail: Any
                try:
                    body = response.json()
                    detail = body.get("detail", body)
                except Exception:
                    detail = response.text
                raise HomeCloudError(
                    f"Request failed ({response.status_code})",
                    status_code=response.status_code,
                    detail=detail,
                )
            last_error = HomeCloudError(
                f"Request failed ({response.status_code})",
                status_code=response.status_code,
            )
            time.sleep(0.5 * (attempt + 1))
        raise last_error or HomeCloudError("Request failed")

    def data_plane_download_to_file(
        self,
        plane: Plane,
        path: str,
        account_id: str,
        dest: Path,
        *,
        url_path: str | None = None,
        params: dict[str, Any] | None = None,
        on_chunk: Callable[[int], None] | None = None,
    ) -> int:
        """Stream a binary response to disk (for large SO objects)."""
        if not self.access_key_id or not self.secret_access_key:
            raise HomeCloudError(
                "Access Key not configured. "
                "Run: homecloud configure, or pass --access-key-id and --secret-access-key"
            )

        dest.parent.mkdir(parents=True, exist_ok=True)

        base_urls = {
            "mq": mq_url(self.apex),
            "so": so_url(self.apex),
            "secrets": secrets_url(self.apex),
        }
        headers = sign_request_headers(
            access_key_id=self.access_key_id,
            secret=self.secret_access_key,
            method="GET",
            path=path,
            account_id=account_id,
        )
        url = f"{base_urls[plane].rstrip('/')}{url_path or path}"
        last_error: HomeCloudError | None = None
        client = self._http()
        download_timeout = httpx.Timeout(30.0, read=None)
        for attempt in range(_MAX_RETRIES + 1):
            try:
                with client.stream(
                    "GET",
                    url,
                    headers=headers,
                    params=params,
                    timeout=download_timeout,
                ) as response:
                    if response.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
                        last_error = HomeCloudError(
                            f"Request failed ({response.status_code})",
                            status_code=response.status_code,
                        )
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    if not response.is_success:
                        detail: Any
                        try:
                            body = response.read()
                            parsed = json.loads(body)
                            detail = parsed.get("detail", parsed)
                        except Exception:
                            detail = response.text or response.reason_phrase
                        raise HomeCloudError(
                            f"Request failed ({response.status_code})",
                            status_code=response.status_code,
                            detail=detail,
                        )

                    nbytes = 0
                    with dest.open("wb") as handle:
                        for chunk in response.iter_bytes(1024 * 1024):
                            handle.write(chunk)
                            chunk_len = len(chunk)
                            nbytes += chunk_len
                            if on_chunk is not None:
                                on_chunk(chunk_len)
                    return nbytes
            except HomeCloudError:
                raise
            except httpx.HTTPError as exc:
                if attempt == _MAX_RETRIES:
                    raise HomeCloudError(f"Request failed: {exc}") from exc
                time.sleep(0.5 * (attempt + 1))
                continue
        raise last_error or HomeCloudError("Request failed")

    def data_plane_request(
        self,
        plane: Plane,
        method: str,
        path: str,
        account_id: str,
        *,
        url_path: str | None = None,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        if not self.access_key_id or not self.secret_access_key:
            raise HomeCloudError(
                "Access Key not configured. "
                "Run: homecloud configure, or pass --access-key-id and --secret-access-key"
            )

        base_urls = {
            "mq": mq_url(self.apex),
            "so": so_url(self.apex),
            "secrets": secrets_url(self.apex),
        }
        base = base_urls[plane]
        headers = sign_request_headers(
            access_key_id=self.access_key_id,
            secret=self.secret_access_key,
            method=method,
            path=path,
            account_id=account_id,
        )
        url = f"{base.rstrip('/')}{url_path or path}"
        return self._request(
            method,
            url,
            headers=headers,
            json=json,
            params=params,
            data=data,
            files=files,
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        last_error: HomeCloudError | None = None
        client = self._http()
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    params=params,
                    data=data,
                    files=files,
                )
            except httpx.HTTPError as exc:
                if attempt == _MAX_RETRIES:
                    raise HomeCloudError(f"Request failed: {exc}") from exc
                time.sleep(0.5 * (attempt + 1))
                continue
            if response.status_code not in _RETRY_STATUS or attempt == _MAX_RETRIES:
                return self._parse(response)
            last_error = HomeCloudError(
                f"Request failed ({response.status_code})",
                status_code=response.status_code,
            )
            time.sleep(0.5 * (attempt + 1))
        raise last_error or HomeCloudError("Request failed")

    def resolve_access_key_account_id(self) -> str:
        if not self.access_key_id or not self.secret_access_key:
            raise HomeCloudError(
                "Access Key not configured. "
                "Run: homecloud configure, or pass --access-key-id and --secret-access-key"
            )

        headers = sign_request_headers(
            access_key_id=self.access_key_id,
            secret=self.secret_access_key,
            method="GET",
            path=WHOAMI_PATH,
            account_id=WHOAMI_ACCOUNT_SENTINEL,
        )
        url = f"{so_url(self.apex).rstrip('/')}{WHOAMI_PATH}"
        data = self._request("GET", url, headers=headers)
        account_id = data.get("account_id")
        if not account_id:
            raise HomeCloudError("Could not resolve account from Access Key")
        return str(account_id)

    @staticmethod
    def _parse(response: httpx.Response) -> Any:
        if response.is_success:
            if not response.content:
                return {}
            try:
                return response.json()
            except ValueError as exc:
                raise HomeCloudError(
                    f"Invalid JSON response ({response.status_code}) from {response.request.url}",
                    status_code=response.status_code,
                ) from exc

        detail: Any
        try:
            body = response.json()
            detail = body.get("detail", body)
        except Exception:
            detail = response.text

        raise HomeCloudError(
            f"Request failed ({response.status_code})",
            status_code=response.status_code,
            detail=detail,
        )
