"""Real-time transfer progress for SO commands (rich, on by default)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn


@dataclass
class SoTransferProgress:
    """Progress bar + per-file status lines for sync / recursive delete."""

    label: str
    total: int
    console: Console = field(default_factory=lambda: Console(stderr=True))
    _progress: Progress | None = field(default=None, init=False, repr=False)
    _task_id: int | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __enter__(self) -> SoTransferProgress:
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
            transient=False,
        )
        self._progress.__enter__()
        self._task_id = self._progress.add_task(self.label, total=max(self.total, 1))
        return self

    def __exit__(self, *args: object) -> None:
        if self._progress is not None:
            self._progress.__exit__(*args)

    def _advance(self) -> None:
        with self._lock:
            if self._progress is not None and self._task_id is not None:
                self._progress.advance(self._task_id)

    def upload(self, key: str) -> None:
        with self._lock:
            self.console.print(f"[green]upload[/]  {key}")
        self._advance()

    def download(self, key: str) -> None:
        with self._lock:
            self.console.print(f"[green]download[/]  {key}")
        self._advance()

    def skip(self, key: str) -> None:
        with self._lock:
            self.console.print(f"[dim]skip[/]    {key}")
        self._advance()

    def delete(self, key: str) -> None:
        with self._lock:
            self.console.print(f"[red]delete[/]  {key}")
        self._advance()

    def message(self, text: str) -> None:
        with self._lock:
            self.console.print(f"[cyan]{text}[/]")
