from __future__ import annotations

import sys

import pytest

from homecloud_cli import bootstrap


def test_should_self_install_requires_explorer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "is_standalone", lambda: True)
    monkeypatch.setattr(bootstrap.os, "name", "nt")
    monkeypatch.setattr(sys, "argv", ["homecloud-windows-amd64.exe"])
    monkeypatch.setattr(bootstrap, "is_running_installed_copy", lambda: False)
    monkeypatch.setattr(bootstrap, "parent_is_explorer", lambda: False)
    monkeypatch.delenv("HOMECLOUD_NO_AUTO_INSTALL", raising=False)
    assert bootstrap.should_self_install() is False


def test_should_self_install_true_for_explorer_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "is_standalone", lambda: True)
    monkeypatch.setattr(bootstrap.os, "name", "nt")
    monkeypatch.setattr(sys, "argv", ["homecloud-windows-amd64.exe"])
    monkeypatch.setattr(bootstrap, "is_running_installed_copy", lambda: False)
    monkeypatch.setattr(bootstrap, "parent_is_explorer", lambda: True)
    monkeypatch.delenv("HOMECLOUD_NO_AUTO_INSTALL", raising=False)
    assert bootstrap.should_self_install() is True


def test_should_self_install_blocked_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "is_standalone", lambda: True)
    monkeypatch.setattr(bootstrap.os, "name", "nt")
    monkeypatch.setattr(sys, "argv", ["homecloud-windows-amd64.exe"])
    monkeypatch.setattr(bootstrap, "is_running_installed_copy", lambda: False)
    monkeypatch.setattr(bootstrap, "parent_is_explorer", lambda: True)
    monkeypatch.setenv("HOMECLOUD_NO_AUTO_INSTALL", "1")
    assert bootstrap.should_self_install() is False


def test_should_self_install_blocked_by_flag() -> None:
    assert bootstrap.should_self_install(no_install_flag=True) is False


def test_consume_no_install_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["homecloud", "--no-install", "version"])
    assert bootstrap.consume_no_install_flag() is True
    assert sys.argv == ["homecloud", "version"]
    assert bootstrap.consume_no_install_flag() is False


def test_maybe_self_install_runs_install(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from homecloud_cli.update import InstallResult
    from pathlib import Path

    monkeypatch.setattr(bootstrap, "consume_no_install_flag", lambda: False)
    monkeypatch.setattr(bootstrap, "should_self_install", lambda **_: True)
    monkeypatch.setattr(
        bootstrap,
        "install_from_running_binary",
        lambda **_: InstallResult(
            version="0.2.36",
            path=Path("C:/x/homecloud.exe"),
            replaced_running=False,
            changed=True,
            path_updated=True,
        ),
    )
    monkeypatch.setattr(bootstrap, "_pause_if_interactive", lambda: None)

    assert bootstrap.maybe_self_install() is True
    out = capsys.readouterr().out
    assert "installed successfully" in out.lower()
    assert "homecloud configure" in out


def test_maybe_self_install_skips_when_not_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "consume_no_install_flag", lambda: False)
    monkeypatch.setattr(bootstrap, "should_self_install", lambda **_: False)
    assert bootstrap.maybe_self_install() is False
