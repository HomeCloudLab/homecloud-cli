from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from homecloud_cli.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_version(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_configure_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    cred_file = tmp_path / "credentials"
    import_file = tmp_path / "import.json"
    import_file.write_text(
        json.dumps(
            {
                "version": 1,
                "access_key_id": "HCAKIMPORT",
                "secret_access_key": "secret",
                "default_account_id": "acc-1",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOMECLOUD_CREDENTIALS_FILE", str(cred_file))

    result = runner.invoke(app, ["configure", "import", str(import_file)])
    assert result.exit_code == 0, result.stdout

    saved = json.loads(cred_file.read_text(encoding="utf-8"))
    assert saved["profiles"]["default"]["access_key_id"] == "HCAKIMPORT"


def test_mq_send_uses_signed_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
) -> None:
    cred_file = tmp_path / "credentials"
    cred_file.write_text(
        json.dumps(
            {
                "version": 1,
                "default_profile": "default",
                "profiles": {
                    "default": {
                        "mq_url": "https://mq.example.test",
                        "default_account_id": "acc-1",
                        "access_key_id": "HCAK1",
                        "secret_access_key": "secret",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOMECLOUD_CREDENTIALS_FILE", str(cred_file))

    captured: dict[str, str] = {}

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method: str, url: str, **kwargs):
            request = httpx.Request(method, url, headers=kwargs.get("headers"), json=kwargs.get("json"))
            captured["method"] = request.method
            captured["path"] = request.url.path
            captured["access_key"] = request.headers.get("X-Homecloud-Access-Key-Id", "")
            captured["signature"] = request.headers.get("X-Homecloud-Signature", "")
            return httpx.Response(200, json={"message_id": "msg-1"})

    monkeypatch.setattr("homecloud_cli.client.httpx.Client", MockHttpClient)

    result = runner.invoke(
        app,
        ["mq", "send", "demo-queue", "--body", '{"hello":"world"}', "--output", "json"],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["method"] == "POST"
    assert captured["path"] == "/acc-1/demo-queue/messages"
    assert captured["access_key"] == "HCAK1"
    assert len(captured["signature"]) == 64
