"""Unified byte-based transfer progress — upload and download share one UI path."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Literal

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from homecloud_core.transfer_state import TransferState

TransferAction = Literal["upload", "download"]
REFRESH_INTERVAL_S = 0.1  # 10 Hz


def format_bytes(n: int) -> str:
    value = float(max(n, 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"


@dataclass
class TransferProgress:
    """Rich progress UI — workers update TransferState; one thread refreshes the bar."""

    label: str
    action: TransferAction
    total_bytes: int
    files_total: int
    console: Console = field(default_factory=lambda: Console(stderr=True))
    state: TransferState = field(init=False)
    _progress: Progress | None = field(default=None, init=False, repr=False)
    _task_id: int | None = field(default=None, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _ui_thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _log_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.state = TransferState(total_bytes=self.total_bytes, files_total=self.files_total)

    def __enter__(self) -> TransferProgress:
        if self.total_bytes > 0:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                DownloadColumn(),
                console=self.console,
                transient=False,
            )
            self._progress.__enter__()
            self._task_id = self._progress.add_task(
                self._description(),
                total=max(self.total_bytes, 1),
            )
        self._stop.clear()
        self._ui_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._ui_thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._stop.set()
        if self._ui_thread is not None:
            self._ui_thread.join(timeout=1.0)
        if self._progress is not None and self._task_id is not None:
            snap = self.state.snapshot()
            self._progress.update(self._task_id, completed=snap.completed_bytes, description=self._description(snap))
        if self._progress is not None:
            self._progress.__exit__(*args)

    def add_bytes(self, nbytes: int) -> None:
        self.state.add_bytes(nbytes)

    def file_begin(self, key: str) -> None:
        self.state.file_begin(key)
        color = "green" if self.action == "upload" else "cyan"
        verb = self.action
        with self._log_lock:
            self.console.print(f"[{color}]{verb}[/]  {key}")

    def file_complete(self, key: str) -> None:
        self.state.file_complete(key)

    def skip(self, key: str) -> None:
        with self._log_lock:
            self.console.print(f"[dim]skip[/]    {key}")

    def delete(self, key: str) -> None:
        with self._log_lock:
            self.console.print(f"[red]delete[/]  {key}")

    def message(self, text: str) -> None:
        with self._log_lock:
            self.console.print(f"[cyan]{text}[/]")

    def _description(self, snap=None) -> str:
        if snap is None:
            snap = self.state.snapshot()
        current = self._current_file_label(snap.active_files)
        return (
            f"{self.label}  |  {snap.files_completed}/{snap.files_total} files"
            f"  |  {current}"
        )

    @staticmethod
    def _current_file_label(active_files: tuple[str, ...]) -> str:
        if not active_files:
            return "—"
        if len(active_files) == 1:
            return active_files[0]
        return f"{len(active_files)} active"

    def _refresh_loop(self) -> None:
        while not self._stop.wait(REFRESH_INTERVAL_S):
            self._refresh_once()
        self._refresh_once()

    def _refresh_once(self) -> None:
        if self._progress is None or self._task_id is None:
            return
        snap = self.state.snapshot()
        self._progress.update(
            self._task_id,
            completed=min(snap.completed_bytes, snap.total_bytes or 1),
            description=self._description(snap),
        )
