"""Self-update helpers for the HomeCloud CLI binary."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from homecloud_cli import __version__
from homecloud_core.errors import HomeCloudError

DEFAULT_RELEASES_BASE = "https://homecloud-cli.so.holab.abrdns.com/releases"
_VERSION_RE = re.compile(r"homecloud\s+(\d+\.\d+\.\d+)")


@dataclass(frozen=True)
class VersionCheck:
    current: str
    latest: str
    update_available: bool
    runtime: str  # "standalone" | "source"


@dataclass(frozen=True)
class InstallResult:
    version: str
    path: Path
    replaced_running: bool
    changed: bool = True
    path_updated: bool = False


def releases_base() -> str:
    return (os.environ.get("HOMECLOUD_INSTALL_URL") or DEFAULT_RELEASES_BASE).rstrip("/")


def is_standalone() -> bool:
    return bool(getattr(sys, "frozen", False))


def normalize_channel(version: str | None) -> str:
    """Return a releases/ path segment: ``latest`` or ``vX.Y.Z``."""
    if version is None or version.strip().lower() in {"", "latest"}:
        return "latest"
    raw = version.strip()
    if raw.lower() == "latest":
        return "latest"
    return raw if raw.startswith("v") else f"v{raw}"


def normalize_version_string(version: str) -> str:
    return version.strip().lstrip("vVv").strip()


def parse_semver(version: str) -> tuple[int, ...]:
    core = normalize_version_string(version).split("+", 1)[0].split("-", 1)[0]
    parts: list[int] = []
    for piece in core.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def platform_artifact() -> tuple[str, str]:
    """Return ``(platform_tag, artifact_filename)`` for the running OS/arch."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        arch = "amd64"
    elif machine in {"aarch64", "arm64"}:
        arch = "arm64"
    else:
        raise HomeCloudError(f"Unsupported architecture for CLI updates: {machine}")

    if system == "linux":
        tag = f"linux-{arch}"
        return tag, f"homecloud-{tag}"
    if system == "darwin":
        tag = f"darwin-{arch}"
        return tag, f"homecloud-{tag}"
    if system == "windows":
        if arch != "amd64":
            raise HomeCloudError("Windows CLI updates are only published for amd64")
        return "windows-amd64", "homecloud-windows-amd64.exe"
    raise HomeCloudError(f"Unsupported OS for CLI updates: {system}")


def fetch_text(url: str, *, timeout: float = 30.0) -> str:
    try:
        response = httpx.get(url, follow_redirects=True, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HomeCloudError(f"Failed to reach release server: {exc}") from exc
    return response.text.strip()


def fetch_latest_version() -> str:
    text = fetch_text(f"{releases_base()}/latest/VERSION")
    if not text:
        raise HomeCloudError("Release server returned an empty VERSION file")
    return normalize_version_string(text)


def check_for_update() -> VersionCheck:
    latest = fetch_latest_version()
    current = normalize_version_string(__version__)
    return VersionCheck(
        current=current,
        latest=latest,
        update_available=parse_semver(latest) > parse_semver(current),
        runtime="standalone" if is_standalone() else "source",
    )


def default_install_dir() -> Path:
    """Same defaults as install.ps1 / install.sh (overridable via HOMECLOUD_INSTALL_DIR)."""
    override = os.environ.get("HOMECLOUD_INSTALL_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / "Programs" / "homecloud"
    return Path.home() / ".local" / "bin"


def install_target_path() -> Path:
    """Path of the binary that ``homecloud update`` writes.

    Standalone replaces the running executable. Source / pip installs the
    published binary into the default install location (same as the installer).
    """
    if is_standalone():
        return Path(sys.executable).resolve()
    name = "homecloud.exe" if os.name == "nt" else "homecloud"
    return default_install_dir() / name


def read_binary_version(path: Path) -> str | None:
    """Return the version reported by an installed ``homecloud`` binary, if any."""
    if not path.is_file():
        return None
    try:
        completed = subprocess.run(
            [str(path), "version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError:
        return None
    output = (completed.stdout or "") + (completed.stderr or "")
    match = _VERSION_RE.search(output)
    if not match:
        return None
    return normalize_version_string(match.group(1))


def path_points_at_standalone(target: Path | None = None) -> bool:
    """True when ``homecloud`` on PATH resolves to the standalone install target."""
    target = (target or install_target_path()).resolve()
    found = shutil.which("homecloud")
    if not found:
        return False
    try:
        return Path(found).resolve() == target
    except OSError:
        return False


def _ensure_dir_on_user_path(directory: Path) -> bool:
    """Put ``directory`` first on the user PATH (Windows). Returns True if changed."""
    if os.name != "nt":
        return False
    try:
        import winreg
    except ImportError:
        return False

    dir_str = str(directory.resolve())
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE
    ) as key:
        try:
            current, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current = ""
        parts = [p for p in str(current).split(";") if p]
        norm = os.path.normcase(dir_str)
        already_first = bool(parts) and os.path.normcase(parts[0]) == norm
        without = [p for p in parts if os.path.normcase(p) != norm]
        if already_first and len(without) == len(parts) - 1:
            return False
        # Prefer the standalone dir first so it wins over pip Scripts.
        new_path = ";".join([dir_str, *without])
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
        return True
    # Do not mutate this process PATH — the parent shell still has the old one.
    # Callers should tell the user to open a new terminal when needed.


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_binary(url: str, dest: Path) -> None:
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as response:
            response.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
    except httpx.HTTPError as exc:
        raise HomeCloudError(f"Download failed ({url}): {exc}") from exc


def _parse_sha256_line(raw: str) -> str | None:
    """Extract a hex digest from a ``sha256sum``-style line (tolerates BOM/CRLF)."""
    text = raw.lstrip("\ufeff").strip()
    if not text:
        return None
    token = text.split()[0].strip().lower()
    if len(token) == 64 and all(c in "0123456789abcdef" for c in token):
        return token
    return None


def _verify_checksum(binary: Path, checksum_url: str) -> None:
    try:
        raw = fetch_text(checksum_url)
    except HomeCloudError:
        return  # checksum optional if missing
    expected = _parse_sha256_line(raw)
    if not expected:
        return
    actual = _sha256_file(binary)
    if actual != expected:
        raise HomeCloudError(
            f"Checksum mismatch — aborting update\n"
            f"  expected: {expected}\n"
            f"  actual:   {actual}"
        )


def _replace_binary(downloaded: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        # Running exe can be renamed on Windows; overwrite in place often fails.
        old = target.with_suffix(target.suffix + ".old")
        if old.exists():
            try:
                old.unlink()
            except OSError:
                pass
        if target.exists():
            try:
                target.replace(old)
            except OSError:
                # Not locked (e.g. installing beside a pip entrypoint) — overwrite.
                try:
                    target.unlink()
                except OSError as exc:
                    raise HomeCloudError(f"Cannot replace {target}: {exc}") from exc
        shutil.move(str(downloaded), str(target))
        try:
            if old.exists():
                old.unlink()
        except OSError:
            pass
    else:
        os.chmod(downloaded, 0o755)
        os.replace(downloaded, target)


def install_version(version: str | None = None, *, force: bool = False) -> InstallResult:
    """Download and install ``latest`` or a pinned ``vX.Y.Z``."""
    channel = normalize_channel(version)
    _platform, artifact = platform_artifact()
    target = install_target_path()
    replaced_running = is_standalone()

    if channel == "latest":
        resolved = fetch_latest_version()
    else:
        resolved = normalize_version_string(channel)

    # Always fetch immutable release assets (not ``latest/``) so VERSION + binary +
    # checksum cannot race while a new release is uploading to latest/.
    asset_channel = f"v{resolved}"

    installed = (
        normalize_version_string(__version__)
        if replaced_running
        else read_binary_version(target)
    )
    if (
        not force
        and installed is not None
        and parse_semver(installed) == parse_semver(resolved)
    ):
        path_updated = False
        if not replaced_running:
            path_updated = _ensure_dir_on_user_path(target.parent)
        return InstallResult(
            version=resolved,
            path=target,
            replaced_running=replaced_running,
            changed=False,
            path_updated=path_updated,
        )

    url = f"{releases_base()}/{asset_channel}/{artifact}"
    checksum_url = f"{url}.sha256"

    with tempfile.TemporaryDirectory(prefix="homecloud-update-") as tmp:
        tmp_path = Path(tmp) / artifact
        _download_binary(url, tmp_path)
        _verify_checksum(tmp_path, checksum_url)
        _replace_binary(tmp_path, target)

    path_updated = False
    if not replaced_running:
        path_updated = _ensure_dir_on_user_path(target.parent)

    return InstallResult(
        version=resolved,
        path=target,
        replaced_running=replaced_running,
        changed=True,
        path_updated=path_updated,
    )
