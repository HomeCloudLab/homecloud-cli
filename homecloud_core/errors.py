from __future__ import annotations

from typing import Any


class HomeCloudError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail

    @property
    def error_payload(self) -> dict[str, Any] | None:
        """Normalized `{code, message, details}` from either envelope or legacy detail dict."""
        if not isinstance(self.detail, dict):
            return None
        error = self.detail.get("error")
        if isinstance(error, dict) and error.get("code"):
            details = error.get("details") if isinstance(error.get("details"), dict) else {}
            return {
                "code": str(error.get("code")),
                "message": str(error.get("message") or error.get("code")),
                "details": details,
            }
        if self.detail.get("code"):
            details = {
                key: value
                for key, value in self.detail.items()
                if key not in {"code", "message"}
            }
            return {
                "code": str(self.detail.get("code")),
                "message": str(self.detail.get("message") or self.detail.get("code")),
                "details": details,
            }
        return None

    @property
    def error_code(self) -> str | None:
        payload = self.error_payload
        return payload["code"] if payload else None

    @property
    def error_details(self) -> dict[str, Any]:
        payload = self.error_payload
        if not payload:
            return {}
        return dict(payload.get("details") or {})


class NotConfiguredError(HomeCloudError):
    pass


class NotLoggedInError(HomeCloudError):
    pass
