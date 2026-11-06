"""Remote MCP JWT export helpers."""

from __future__ import annotations

from typer.testing import CliRunner

from homecloud_cli.cli import app

runner = CliRunner()


def test_mcp_print_token_requires_session(monkeypatch):
    monkeypatch.setattr(
        "homecloud_core.session.get_access_token",
        lambda _profile: None,
    )
    result = runner.invoke(app, ["mcp", "print-token"])
    assert result.exit_code == 1
    assert "No Console JWT" in (result.stderr or result.stdout)


def test_mcp_env_bash(monkeypatch):
    monkeypatch.setattr(
        "homecloud_core.session.get_access_token",
        lambda _profile: "jwt-test-token",
    )
    result = runner.invoke(app, ["mcp", "env"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "export HC_ACCESS_TOKEN=jwt-test-token"


def test_mcp_env_powershell(monkeypatch):
    monkeypatch.setattr(
        "homecloud_core.session.get_access_token",
        lambda _profile: "jwt-test-token",
    )
    result = runner.invoke(app, ["mcp", "env", "--shell", "powershell"])
    assert result.exit_code == 0
    assert '$env:HC_ACCESS_TOKEN = "jwt-test-token"' in result.stdout
