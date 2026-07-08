"""Thread-safe transfer metrics for upload/download progress."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class TransferSnapshot:
    total_bytes: int
    completed_bytes: int
    files_total: int
    files_completed: int
    active_files: tuple[str, ...]
    bytes_per_second: float
    eta_seconds: float | None


class TransferState:
    """Mutable transfer counters — workers update via add_bytes / file_* only."""

    def __init__(self, *, total_bytes: int, files_total: int) -> None:
        self.total_bytes = max(total_bytes, 0)
        self.files_total = max(files_total, 0)
        self._completed_bytes = 0
        self._files_completed = 0
        self._active_files: list[str] = []
        self._lock = threading.Lock()
        self._started_at = time.monotonic()

    def add_bytes(self, nbytes: int) -> None:
        if nbytes <= 0:
            return
        with self._lock:
            self._completed_bytes += nbytes

    def file_begin(self, key: str) -> None:
        with self._lock:
            if key not in self._active_files:
                self._active_files.append(key)

    def file_complete(self, key: str) -> None:
        with self._lock:
            if key in self._active_files:
                self._active_files.remove(key)
            self._files_completed += 1

    def snapshot(self) -> TransferSnapshot:
        with self._lock:
            elapsed = max(time.monotonic() - self._started_at, 0.001)
            completed = self._completed_bytes
            speed = completed / elapsed
            remaining = max(self.total_bytes - completed, 0)
            eta = remaining / speed if speed > 0 and remaining > 0 else None
            return TransferSnapshot(
                total_bytes=self.total_bytes,
                completed_bytes=completed,
                files_total=self.files_total,
                files_completed=self._files_completed,
                active_files=tuple(self._active_files),
                bytes_per_second=speed,
                eta_seconds=eta,
            )
