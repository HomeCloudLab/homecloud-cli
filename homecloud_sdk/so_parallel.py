"""Parallel SO transfer helpers."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_SO_WORKERS = 10


def run_parallel(
    items: list[str],
    worker: Callable[[str], None],
    *,
    max_workers: int = DEFAULT_SO_WORKERS,
) -> None:
    if not items:
        return

    workers = max(1, min(max_workers, len(items)))
    if workers == 1:
        for item in items:
            worker(item)
        return

    errors: list[BaseException] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(worker, item): item for item in items}
        for future in as_completed(futures):
            try:
                future.result()
            except BaseException as exc:
                errors.append(exc)

    if errors:
        if len(errors) == 1:
            raise errors[0]
        raise errors[0]
