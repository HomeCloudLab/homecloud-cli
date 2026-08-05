from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from homecloud_cli.cli import app
from homecloud_cli.update import (
    check_for_update,
    normalize_channel,
    parse_semver,
    platform_artifact,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_normalize_channel() -> None:
    assert normalize_channel(None) == "latest"
    assert normalize_channel("latest") == "latest"
    assert normalize_channel("0.2.29") == "v0.2.29"
    assert normalize_channel("v0.2.29") == "v0.2.29"


def test_parse_semver() -> None:
    assert parse_semver("0.2.29") > parse_semver("0.2.26")
    assert parse_semver("v1.0.0") == parse_semver("1.0.0")


def test_platform_artifact_smoke() -> None:
    tag, artifact = platform_artifact()
    assert tag
    assert artifact.startswith("homecloud-")


def test_check_for_update(monkeypatch: pytest.MonkeyPatch) -> None:
    from homecloud_cli import update as update_mod

    monkeypatch.setattr(update_mod, "fetch_latest_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "__version__", "0.2.29")
    info = check_for_update()
    assert info.latest == "9.9.9"
    assert info.update_available is True


def test_update_check_cli(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    from homecloud_cli import update as update_mod

    monkeypatch.setattr(
        update_mod,
        "check_for_update",
        lambda: update_mod.VersionCheck(
            current="0.2.29",
            latest="9.9.9",
            update_available=True,
            runtime="source",
        ),
    )
    result = runner.invoke(app, ["update", "--check"])
    assert result.exit_code == 2
    assert "9.9.9" in result.stdout
    assert "Update available" in result.stdout
    assert "Traceback" not in result.stdout


def test_update_from_source_installs_binary(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path
) -> None:
    from homecloud_cli import update as update_mod

    target = tmp_path / "homecloud.exe"

    monkeypatch.setattr(update_mod, "is_standalone", lambda: False)
    monkeypatch.setattr(
        update_mod,
        "install_version",
        lambda *_a, **_k: update_mod.InstallResult(
            version="9.9.9",
            path=target,
            replaced_running=False,
            changed=True,
            path_updated=True,
        ),
    )
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Installed homecloud 9.9.9" in result.stdout
    assert "new terminal" in result.stdout.lower()


def test_update_skips_when_binary_already_current(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path
) -> None:
    from homecloud_cli import update as update_mod

    target = tmp_path / "homecloud.exe"
    monkeypatch.setattr(
        update_mod,
        "install_version",
        lambda *_a, **_k: update_mod.InstallResult(
            version="0.2.31",
            path=target,
            replaced_running=False,
            changed=False,
            path_updated=False,
        ),
    )
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert result.stdout.strip().splitlines() == [
        "Checking for updates…",
        "Already up to date (0.2.31).",
    ]


def test_install_version_replaces_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from homecloud_cli import update as update_mod

    target = tmp_path / "homecloud.exe"
    target.write_bytes(b"old")

    monkeypatch.setattr(update_mod, "is_standalone", lambda: True)
    monkeypatch.setattr(update_mod, "install_target_path", lambda: target)
    monkeypatch.setattr(update_mod, "platform_artifact", lambda: ("windows-amd64", "bin.exe"))
    monkeypatch.setattr(update_mod, "fetch_latest_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "__version__", "0.2.29")

    def fake_download(url: str, dest: Path) -> None:
        dest.write_bytes(b"new-binary")

    monkeypatch.setattr(update_mod, "_download_binary", fake_download)
    monkeypatch.setattr(update_mod, "_verify_checksum", lambda *_a, **_k: None)

    installed = update_mod.install_version("latest")
    assert installed.version == "9.9.9"
    assert installed.path == target
    assert target.read_bytes() == b"new-binary"


def test_install_target_path_source_uses_default_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from homecloud_cli import update as update_mod

    monkeypatch.setattr(update_mod, "is_standalone", lambda: False)
    monkeypatch.setattr(update_mod, "default_install_dir", lambda: tmp_path)
    path = update_mod.install_target_path()
    assert path.parent == tmp_path
    assert path.name in {"homecloud", "homecloud.exe"}


def test_install_target_path_standalone_uses_default_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Update/install always write to the install dir, not Downloads."""
    from homecloud_cli import update as update_mod

    monkeypatch.setattr(update_mod, "is_standalone", lambda: True)
    monkeypatch.setattr(update_mod, "default_install_dir", lambda: tmp_path)
    monkeypatch.setattr(update_mod.sys, "executable", str(tmp_path / "Downloads" / "homecloud.exe"))
    path = update_mod.install_target_path()
    assert path == tmp_path / update_mod.binary_name()


def test_default_install_dir_windows_homecloud(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Windows default dir is Programs\\HomeCloud (skip Path flavor issues on Linux CI)."""
    import os

    from homecloud_cli import update as update_mod

    if os.name != "nt":
        pytest.skip("WindowsPath cannot be constructed on POSIX when os.name is patched")

    monkeypatch.delenv("HOMECLOUD_INSTALL_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert update_mod.default_install_dir() == tmp_path / "Programs" / "HomeCloud"
    assert update_mod.legacy_install_dir() == tmp_path / "Programs" / "homecloud"


def test_default_install_dir_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from homecloud_cli import update as update_mod

    monkeypatch.setenv("HOMECLOUD_INSTALL_DIR", str(tmp_path / "custom"))
    assert update_mod.default_install_dir() == tmp_path / "custom"
    assert update_mod.legacy_install_dir() is None


def test_install_from_running_binary_copies_and_verifies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from homecloud_cli import update as update_mod

    source = tmp_path / "download.exe"
    source.write_bytes(b"homecloud-binary-v1")
    install_dir = tmp_path / "HomeCloud"
    target = install_dir / "homecloud.exe"

    monkeypatch.setattr(update_mod, "is_standalone", lambda: True)
    monkeypatch.setattr(update_mod.sys, "executable", str(source))
    monkeypatch.setattr(update_mod, "install_target_path", lambda: target)
    monkeypatch.setattr(update_mod, "__version__", "0.2.36")
    monkeypatch.setattr(update_mod, "read_binary_version", lambda _p: None)
    monkeypatch.setattr(update_mod, "_ensure_install_path", lambda _p: True)

    result = update_mod.install_from_running_binary()
    assert result.changed is True
    assert result.path_updated is True
    assert result.skipped_reason is None
    assert target.read_bytes() == b"homecloud-binary-v1"
    assert update_mod._sha256_file(source) == update_mod._sha256_file(target)


def test_install_from_running_binary_skips_same_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from homecloud_cli import update as update_mod

    source = tmp_path / "download.exe"
    source.write_bytes(b"same")
    target = tmp_path / "HomeCloud" / "homecloud.exe"
    target.parent.mkdir()
    target.write_bytes(b"installed")

    monkeypatch.setattr(update_mod, "is_standalone", lambda: True)
    monkeypatch.setattr(update_mod.sys, "executable", str(source))
    monkeypatch.setattr(update_mod, "install_target_path", lambda: target)
    monkeypatch.setattr(update_mod, "__version__", "0.2.36")
    monkeypatch.setattr(update_mod, "read_binary_version", lambda _p: "0.2.36")
    monkeypatch.setattr(update_mod, "_ensure_install_path", lambda _p: False)

    result = update_mod.install_from_running_binary()
    assert result.changed is False
    assert result.skipped_reason == "same_version"
    assert target.read_bytes() == b"installed"


def test_install_from_running_binary_refuses_downgrade_without_force(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from homecloud_cli import update as update_mod

    source = tmp_path / "download.exe"
    source.write_bytes(b"old")
    target = tmp_path / "homecloud.exe"
    target.write_bytes(b"new")

    monkeypatch.setattr(update_mod, "is_standalone", lambda: True)
    monkeypatch.setattr(update_mod.sys, "executable", str(source))
    monkeypatch.setattr(update_mod, "install_target_path", lambda: target)
    monkeypatch.setattr(update_mod, "__version__", "0.2.30")
    monkeypatch.setattr(update_mod, "read_binary_version", lambda _p: "0.2.40")

    result = update_mod.install_from_running_binary()
    assert result.changed is False
    assert result.skipped_reason == "newer_installed"
    assert target.read_bytes() == b"new"

    monkeypatch.setattr(update_mod, "_ensure_install_path", lambda _p: False)
    forced = update_mod.install_from_running_binary(force=True)
    assert forced.changed is True
    assert target.read_bytes() == b"old"


def test_install_version_downloads_pinned_channel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from homecloud_cli import update as update_mod

    target = tmp_path / "homecloud.exe"
    seen: dict[str, str] = {}

    monkeypatch.setattr(update_mod, "is_standalone", lambda: False)
    monkeypatch.setattr(update_mod, "install_target_path", lambda: target)
    monkeypatch.setattr(update_mod, "platform_artifact", lambda: ("windows-amd64", "bin.exe"))
    monkeypatch.setattr(update_mod, "fetch_latest_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "_ensure_install_path", lambda _p: False)

    def fake_download(url: str, dest: Path) -> None:
        seen["url"] = url
        dest.write_bytes(b"new-binary")

    def fake_verify(binary: Path, checksum_url: str) -> None:
        seen["checksum_url"] = checksum_url

    monkeypatch.setattr(update_mod, "_download_binary", fake_download)
    monkeypatch.setattr(update_mod, "_verify_checksum", fake_verify)
    monkeypatch.setattr(update_mod, "read_binary_version", lambda _p: "0.1.0")

    result = update_mod.install_version("latest")
    assert result.version == "9.9.9"
    assert result.changed is True
    assert "/releases/v9.9.9/" in seen["url"]
    assert "/releases/latest/" not in seen["url"]
    assert seen["checksum_url"].endswith(".sha256")


def test_install_version_skips_download_when_target_current(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from homecloud_cli import update as update_mod

    target = tmp_path / "homecloud.exe"
    target.write_bytes(b"binary")
    called = {"download": False}

    monkeypatch.setattr(update_mod, "is_standalone", lambda: False)
    monkeypatch.setattr(update_mod, "install_target_path", lambda: target)
    monkeypatch.setattr(update_mod, "fetch_latest_version", lambda: "0.2.31")
    monkeypatch.setattr(update_mod, "read_binary_version", lambda _p: "0.2.31")
    monkeypatch.setattr(update_mod, "_ensure_install_path", lambda _p: False)
    monkeypatch.setattr(
        update_mod,
        "_download_binary",
        lambda *_a, **_k: called.__setitem__("download", True),
    )

    result = update_mod.install_version("latest")
    assert result.changed is False
    assert result.version == "0.2.31"
    assert called["download"] is False


def test_uninstall_standalone_removes_binary_and_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from homecloud_cli import update as update_mod
    from homecloud_core.errors import HomeCloudError

    install_dir = tmp_path / "HomeCloud"
    target = install_dir / update_mod.binary_name()
    install_dir.mkdir()
    target.write_bytes(b"bin")

    path_calls = {"n": 0}

    def fake_remove_path(_dirs: list[Path]) -> bool:
        path_calls["n"] += 1
        return path_calls["n"] == 1

    monkeypatch.setattr(update_mod, "default_install_dir", lambda: install_dir)
    monkeypatch.setattr(update_mod, "legacy_install_dir", lambda: None)
    monkeypatch.setattr(update_mod, "is_standalone", lambda: False)
    monkeypatch.setattr(update_mod, "_remove_dirs_from_user_path", fake_remove_path)

    result = update_mod.uninstall_standalone()
    assert target in result.removed_paths
    assert not target.exists()
    assert result.path_updated is True
    assert not install_dir.exists()

    with pytest.raises(HomeCloudError, match="No HomeCloud CLI"):
        update_mod.uninstall_standalone()


def test_uninstall_cmd(runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from homecloud_cli import update as update_mod

    monkeypatch.setattr(
        update_mod,
        "uninstall_standalone",
        lambda: update_mod.UninstallResult(
            removed_paths=(tmp_path / "homecloud.exe",),
            path_updated=True,
            running_binary_deferred=False,
        ),
    )
    monkeypatch.setattr(update_mod, "install_target_path", lambda: tmp_path / "homecloud.exe")
    result = runner.invoke(app, ["uninstall", "--yes"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "uninstalled" in result.stdout.lower()
    assert "PATH" in result.stdout


def test_parse_sha256_line() -> None:
    from homecloud_cli.update import _parse_sha256_line

    digest = "6b69b46a888723540e4bcd24a290ff537e8accb730f35e322d23cab31d8541e0"
    assert _parse_sha256_line(f"{digest}  homecloud-windows-amd64.exe\r\n") == digest
    assert _parse_sha256_line(f"\ufeff{digest}  file") == digest
    assert _parse_sha256_line("not-a-hash") is None


def test_fetch_latest_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from homecloud_cli import update as update_mod
    from homecloud_core.errors import HomeCloudError

    def boom(*_a, **_k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(update_mod.httpx, "get", boom)
    with pytest.raises(HomeCloudError, match="Failed to reach"):
        update_mod.fetch_latest_version()
