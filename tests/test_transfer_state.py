"""Tests for thread-safe transfer state."""

from concurrent.futures import ThreadPoolExecutor

from homecloud_core.transfer_state import TransferState


def test_transfer_state_tracks_bytes_and_files() -> None:
    state = TransferState(total_bytes=1000, files_total=2)
    state.file_begin("a.txt")
    state.add_bytes(400)
    state.file_complete("a.txt")
    snap = state.snapshot()
    assert snap.completed_bytes == 400
    assert snap.files_completed == 1
    assert snap.active_files == ()


def test_transfer_state_thread_safe_bytes() -> None:
    state = TransferState(total_bytes=10_000, files_total=10)

    def worker() -> None:
        state.file_begin("part")
        for _ in range(100):
            state.add_bytes(10)
        state.file_complete("part")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: worker(), range(10)))

    snap = state.snapshot()
    assert snap.completed_bytes == 10_000
    assert snap.files_completed == 10
