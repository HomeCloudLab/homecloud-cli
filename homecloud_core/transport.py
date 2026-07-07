"""Unified HTTP transport — auth and routing are internal."""

from __future__ import annotations

import time
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
    ) -> None:
        self.apex = apex
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.access_token = access_token
        self.timeout = timeout

    def console_request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        require_auth: bool = True,
    ) -> Any:
        if require_auth and not self.access_token:
            raise NotLoggedInError("Not logged in. Run: homecloud login")

        headers: dict[str, str] = {}
        if require_auth and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        url = urljoin(console_url(self.apex).rstrip("/") + "/", path.lstrip("/"))
        return self._request(method, url, headers=headers, json=json, params=params)

    def data_plane_request_bytes(
        self,
        plane: Plane,
        method: str,
        path: str,
        account_id: str,
        *,
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
        url = f"{base_urls[plane].rstrip('/')}{path}"
        last_error: HomeCloudError | None = None
        for attempt in range(_MAX_RETRIES + 1):
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(method, url, headers=headers, params=params)
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

    def data_plane_request(
        self,
        plane: Plane,
        method: str,
        path: str,
        account_id: str,
        *,
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
        url = f"{base.rstrip('/')}{path}"
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
        for attempt in range(_MAX_RETRIES + 1):
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    params=params,
                    data=data,
                    files=files,
                )
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
            return response.json()

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
