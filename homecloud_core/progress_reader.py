"""File-like wrapper that reports bytes read for upload progress."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ProgressReader:
    """Wrap a binary file handle; call on_bytes with each read() length."""

    def __init__(
        self,
        wrapped: Any,
        on_bytes: Callable[[int], None] | None,
    ) -> None:
        self._wrapped = wrapped
        self._on_bytes = on_bytes

    def read(self, size: int = -1) -> bytes:
        data = self._wrapped.read(size)
        if data and self._on_bytes is not None:
            self._on_bytes(len(data))
        return data

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)
