"""First-run / double-click self-install for the standalone Windows CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from homecloud_core.errors import HomeCloudError

from homecloud_cli.update import (
    InstallResult,
    default_install_dir,
    install_from_running_binary,
    install_target_path,
    is_running_installed_copy,
    is_standalone,
    legacy_install_dir,
)


def _env_truthy(name: str) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def consume_no_install_flag() -> bool:
    """Remove ``--no-install`` from ``sys.argv``. Return True if it was present."""
    if "--no-install" not in sys.argv:
        return False
    sys.argv = [arg for arg in sys.argv if arg != "--no-install"]
    return True


def parent_process_name() -> str | None:
    """Best-effort parent executable name (Windows). None if unknown."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        pid = int(kernel32.GetCurrentProcessId())
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap in (-1, 0xFFFFFFFF):
            return None
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if not kernel32.Process32FirstW(snap, ctypes.byref(entry)):
                return None
            parent_pid: int | None = None
            while True:
                if int(entry.th32ProcessID) == pid:
                    parent_pid = int(entry.th32ParentProcessID)
                    break
                if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                    break
            if parent_pid is None:
                return None
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if not kernel32.Process32FirstW(snap, ctypes.byref(entry)):
                return None
            while True:
                if int(entry.th32ProcessID) == parent_pid:
                    return str(entry.szExeFile)
                if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                    break
            return None
        finally:
            kernel32.CloseHandle(snap)
    except Exception:
        return None


def parent_is_explorer() -> bool:
    """Heuristic: launched via Explorer double-click (not a guarantee)."""
    name = parent_process_name()
    if not name:
        return False
    return Path(name).name.lower() == "explorer.exe"


def should_self_install(*, no_install_flag: bool = False) -> bool:
    """Layered signals for automatic install on double-click."""
    if no_install_flag:
        return False
    if _env_truthy("HOMECLOUD_NO_AUTO_INSTALL"):
        return False
    if not is_standalone():
        return False
    if os.name != "nt":
        return False
    # Only bare invocation (no subcommand / options left after stripping overrides).
    if len(sys.argv) != 1:
        return False
    if is_running_installed_copy():
        return False
    if not parent_is_explorer():
        return False
    return True


def _pause_if_interactive() -> None:
    if not sys.stdin.isatty():
        return
    try:
        input("\nPress Enter to close...")
    except EOFError:
        pass


def _print_install_outcome(result: InstallResult, *, pause: bool) -> None:
    path = result.path
    if result.skipped_reason == "same_version":
        print(f"HomeCloud CLI {result.version} is already installed.")
        print()
        print(f"Location:\n  {path}")
        if result.path_updated:
            print("\nPATH updated. Open a new terminal to use `homecloud`.")
        else:
            print("\nOpen a new terminal and run `homecloud`, or:")
            print("  homecloud update")
            print("  homecloud install --force")
    elif result.skipped_reason == "newer_installed":
        print(
            f"A newer HomeCloud CLI ({result.version}) is already installed at:\n  {path}"
        )
        print("\nThis binary was not installed. To overwrite, run:")
        print("  homecloud install --force")
    elif result.changed:
        print("HomeCloud CLI installed successfully!")
        print()
        print(f"Location:\n  {path}")
        if result.path_updated:
            print("\nPATH updated.")
        else:
            print("\nPATH already configured.")
        print("\nOpen a new terminal and run:\n")
        print("  homecloud configure")
        print("\nor\n")
        print("  homecloud login")
    else:
        print(f"HomeCloud CLI {result.version} is ready at:\n  {path}")

    if pause:
        _pause_if_interactive()


def maybe_self_install() -> bool:
    """If this looks like an Explorer double-click, install and return True.

    ``main()`` should return immediately when this returns True (do not run Typer).
    """
    no_install = consume_no_install_flag()
    if not should_self_install(no_install_flag=no_install):
        return False

    print("Installing HomeCloud CLI...")
    try:
        result = install_from_running_binary(force=False)
    except HomeCloudError as exc:
        print(f"Installation failed: {exc}", file=sys.stderr)
        _pause_if_interactive()
        raise SystemExit(1) from exc

    if result.changed:
        print("  Binary copied")
        print("  SHA256 verified")
        if result.path_updated:
            print("  PATH updated")
        else:
            print("  PATH already configured")
        print()

    _print_install_outcome(result, pause=True)
    return True


def print_cli_install_result(result: InstallResult) -> None:
    """User-facing summary for ``homecloud install`` (no pause)."""
    _print_install_outcome(result, pause=False)


def install_dir_hint() -> Path:
    return default_install_dir()


def target_hint() -> Path:
    return install_target_path()


def legacy_dir_hint() -> Path | None:
    return legacy_install_dir()
