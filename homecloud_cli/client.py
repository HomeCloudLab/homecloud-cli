"""HTTP clients for console API and signed data-plane requests."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from homecloud_cli.config import Profile
from homecloud_cli.signing import sign_request_headers


class HomeCloudError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class ConsoleClient:
    def __init__(self, profile: Profile, *, timeout: float = 30.0) -> None:
        self.profile = profile
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        token = self.profile.require_console_token()
        return {"Authorization": f"Bearer {token}"}

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = urljoin(self.profile.console_url.rstrip("/") + "/", path.lstrip("/"))
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, url, headers=self._headers(), **kwargs)
        return self._parse(response)

    def login(self, email: str, password: str) -> str:
        url = urljoin(self.profile.console_url.rstrip("/") + "/", "auth/login")
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, json={"email": email, "password": password})
        data = self._parse(response)
        token = data.get("access_token")
        if not token:
            raise HomeCloudError("Login response missing access_token")
        return token

    def list_accounts(self) -> list[dict[str, Any]]:
        data = self.request("GET", "accounts")
        return data.get("items", data if isinstance(data, list) else [])

    def list_queues(self, account_id: str) -> list[dict[str, Any]]:
        data = self.request("GET", f"accounts/{account_id}/queues")
        return data.get("items", [])

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


class DataPlaneClient:
    def __init__(self, profile: Profile, *, base_url: str, timeout: float = 60.0) -> None:
        self.profile = profile
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def signed_request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        account_id, access_key_id, secret = self.profile.require_access_key()
        headers = sign_request_headers(
            access_key_id=access_key_id,
            secret=secret,
            method=method,
            path=path,
            account_id=account_id,
        )
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, url, headers=headers, json=json, params=params)
        return ConsoleClient._parse(response)


class MqClient(DataPlaneClient):
    def __init__(self, profile: Profile, *, timeout: float = 60.0) -> None:
        super().__init__(profile, base_url=profile.mq_url, timeout=timeout)

    def send_message(self, queue_name: str, *, body: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
        account_id, _, _ = self.profile.require_access_key()
        path = f"/{account_id}/{queue_name}/messages"
        payload: dict[str, Any] = {"body": body}
        if headers:
            payload["headers"] = headers
        return self.signed_request("POST", path, json=payload)

    def receive_messages(
        self,
        queue_name: str,
        *,
        max_messages: int = 1,
        wait_seconds: int = 20,
    ) -> list[dict[str, Any]]:
        account_id, _, _ = self.profile.require_access_key()
        path = f"/{account_id}/{queue_name}/messages"
        data = self.signed_request(
            "GET",
            path,
            params={"max_messages": max_messages, "wait_seconds": wait_seconds},
        )
        return data.get("items", [])
