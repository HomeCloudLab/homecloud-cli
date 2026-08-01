"""Self-update helpers for the standalone HomeCloud CLI binary."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from homecloud_cli import __version__
from homecloud_core.errors import HomeCloudError

DEFAULT_RELEASES_BASE = "https://homecloud-cli.so.holab.abrdns.com/releases"


@dataclass(frozen=True)
class VersionCheck:
    current: str
    latest: str
    update_available: bool
    runtime: str  # "standalone" | "source"


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


def install_target_path() -> Path:
    """Path of the binary that ``homecloud update`` should replace."""
    if is_standalone():
        return Path(sys.executable).resolve()
    raise HomeCloudError(
        "This CLI is a source install (pip), not a standalone binary.\n"
        "Install or upgrade the binary with the installer, or upgrade the package in this environment."
    )


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


def _verify_checksum(binary: Path, checksum_url: str) -> None:
    try:
        raw = fetch_text(checksum_url)
    except HomeCloudError:
        return  # checksum optional if missing
    expected = raw.split()[0].strip().lower() if raw else ""
    if not expected:
        return
    actual = _sha256_file(binary)
    if actual != expected:
        raise HomeCloudError("Checksum mismatch — aborting update")


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
            target.replace(old)
        shutil.move(str(downloaded), str(target))
        try:
            old.unlink()
        except OSError:
            pass
    else:
        os.chmod(downloaded, 0o755)
        os.replace(downloaded, target)


def install_version(version: str | None = None) -> str:
    """Download and install ``latest`` or a pinned ``vX.Y.Z``. Returns installed version string."""
    channel = normalize_channel(version)
    _platform, artifact = platform_artifact()
    target = install_target_path()

    if channel == "latest":
        resolved = fetch_latest_version()
    else:
        resolved = normalize_version_string(channel)

    current = normalize_version_string(__version__)
    if channel == "latest" and parse_semver(resolved) == parse_semver(current):
        return current

    url = f"{releases_base()}/{channel}/{artifact}"
    checksum_url = f"{url}.sha256"

    with tempfile.TemporaryDirectory(prefix="homecloud-update-") as tmp:
        tmp_path = Path(tmp) / artifact
        _download_binary(url, tmp_path)
        _verify_checksum(tmp_path, checksum_url)
        _replace_binary(tmp_path, target)

    return resolved
