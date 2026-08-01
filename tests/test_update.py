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
        "check_for_update",
        lambda: update_mod.VersionCheck(
            current="0.2.29",
            latest="9.9.9",
            update_available=True,
            runtime="source",
        ),
    )
    monkeypatch.setattr(
        update_mod,
        "install_version",
        lambda *_a, **_k: update_mod.InstallResult(
            version="9.9.9", path=target, replaced_running=False
        ),
    )
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Installed homecloud 9.9.9" in result.stdout
    assert "new terminal" in result.stdout.lower()


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


def test_fetch_latest_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from homecloud_cli import update as update_mod
    from homecloud_core.errors import HomeCloudError

    def boom(*_a, **_k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(update_mod.httpx, "get", boom)
    with pytest.raises(HomeCloudError, match="Failed to reach"):
        update_mod.fetch_latest_version()
