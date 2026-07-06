from __future__ import annotations

from typing import Any


class HomeCloudError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class NotConfiguredError(HomeCloudError):
    pass


class NotLoggedInError(HomeCloudError):
    pass
