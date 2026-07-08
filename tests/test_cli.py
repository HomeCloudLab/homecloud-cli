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
    assert "0.2.17" in result.stdout

    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "homecloud 0.2.17" in result.stdout


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
    monkeypatch.setenv("HOMECLOUD_CONFIG_DIR", str(tmp_path))

    result = runner.invoke(app, ["configure", "import", str(import_file)])
    assert result.exit_code == 0, result.stdout

    saved = json.loads(cred_file.read_text(encoding="utf-8"))
    assert saved["profiles"]["default"]["access_key_id"] == "HCAKIMPORT"


def test_mq_send_delegates_to_sdk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
) -> None:
    cred_file = tmp_path / "credentials"
    cred_file.write_text(
        json.dumps(
            {
                "version": 2,
                "default_profile": "default",
                "profiles": {
                    "default": {
                        "apex": "example.test",
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
    monkeypatch.setenv("HOMECLOUD_CONFIG_DIR", str(tmp_path))

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
            return httpx.Response(200, json={"message_id": "msg-1"})

    monkeypatch.setattr("homecloud_core.transport.httpx.Client", MockHttpClient)

    result = runner.invoke(
        app,
        ["mq", "send", "demo-queue", "--body", '{"hello":"world"}', "--output", "json"],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["method"] == "POST"
    assert captured["path"] == "/acc-1/demo-queue/messages"


def test_mq_send_powershell_mangled_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
) -> None:
    cred_file = tmp_path / "credentials"
    cred_file.write_text(
        json.dumps(
            {
                "version": 2,
                "default_profile": "default",
                "profiles": {
                    "default": {
                        "apex": "example.test",
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
    monkeypatch.setenv("HOMECLOUD_CONFIG_DIR", str(tmp_path))

    captured: dict[str, object] = {}

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method: str, url: str, **kwargs):
            captured["json"] = kwargs.get("json")
            return httpx.Response(200, json={"message_id": "msg-1"})

    monkeypatch.setattr("homecloud_core.transport.httpx.Client", MockHttpClient)

    result = runner.invoke(
        app,
        ["mq", "send", "demo-queue", "--body", "{hello:world}", "--output", "json"],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["json"] == {"body": '{"hello": "world"}'}


def test_mq_send_invalid_json_shows_helpful_error(runner: CliRunner) -> None:
    result = runner.invoke(app, ["mq", "send", "q", "--body", "not-json"])
    assert result.exit_code == 1
    combined = result.stdout + result.stderr
    assert "Invalid JSON in --body" in combined
    assert "PowerShell" in combined


def test_mq_send_unknown_queue_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
) -> None:
    cred_file = tmp_path / "credentials"
    cred_file.write_text(
        json.dumps(
            {
                "version": 2,
                "default_profile": "default",
                "profiles": {
                    "default": {
                        "apex": "holab.abrdns.com",
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
    monkeypatch.setenv("HOMECLOUD_CONFIG_DIR", str(tmp_path))

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method: str, url: str, **kwargs):
            return httpx.Response(404, json={"detail": "Queue not found"})

    monkeypatch.setattr("homecloud_core.transport.httpx.Client", MockHttpClient)

    result = runner.invoke(
        app,
        ["mq", "send", "no-such-queue", "--body", '{"hello":"world"}'],
    )
    assert result.exit_code == 1
    assert "Queue 'no-such-queue' not found" in (result.stdout + result.stderr)


def test_login_sends_username(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
) -> None:
    monkeypatch.setenv("HOMECLOUD_CONFIG_DIR", str(tmp_path))

    captured: dict[str, object] = {}

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method: str, url: str, **kwargs):
            if method == "POST" and "auth/login" in url:
                captured["json"] = kwargs.get("json")
            return httpx.Response(200, json={"access_token": "tok-1"})

    monkeypatch.setattr("homecloud_core.transport.httpx.Client", MockHttpClient)

    result = runner.invoke(
        app,
        ["login", "--username", "alice", "--password", "secret123"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert captured["json"] == {"username": "alice", "password": "secret123"}


def test_so_sync_uploads_new_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
) -> None:
    cred_file = tmp_path / "credentials"
    cred_file.write_text(
        json.dumps(
            {
                "version": 2,
                "default_profile": "default",
                "profiles": {
                    "default": {
                        "apex": "example.test",
                        "access_key_id": "HCAK1",
                        "secret_access_key": "secret",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOMECLOUD_CREDENTIALS_FILE", str(cred_file))
    monkeypatch.setenv("HOMECLOUD_CONFIG_DIR", str(tmp_path))

    local = tmp_path / "dist"
    local.mkdir()
    (local / "index.html").write_text("<html></html>", encoding="utf-8")

    calls: list[tuple[str, str]] = []

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method: str, url: str, **kwargs):
            if "/access-key/whoami" in url:
                return httpx.Response(
                    200,
                    json={"account_id": "acc-1", "account_short_id": "acct"},
                )
            if method == "GET" and "/objects" in url and "multipart" not in url:
                return httpx.Response(
                    200,
                    json={"items": [], "total": 0, "pages": 1, "page": 1, "page_size": 100},
                )
            if method == "POST" and "/objects" in url:
                calls.append(("upload", kwargs.get("data", {}).get("key", "")))
                return httpx.Response(201, json={"key": "index.html"})
            return httpx.Response(404)

    monkeypatch.setattr("homecloud_core.transport.httpx.Client", MockHttpClient)

    result = runner.invoke(
        app,
        ["so", "sync", str(local), "so://my-bucket/", "--output", "json"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert ("upload", "index.html") in calls


def test_so_sync_overwrites_same_size_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
) -> None:
    cred_file = tmp_path / "credentials"
    cred_file.write_text(
        json.dumps(
            {
                "version": 2,
                "default_profile": "default",
                "profiles": {
                    "default": {
                        "apex": "example.test",
                        "access_key_id": "HCAK1",
                        "secret_access_key": "secret",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOMECLOUD_CREDENTIALS_FILE", str(cred_file))
    monkeypatch.setenv("HOMECLOUD_CONFIG_DIR", str(tmp_path))

    local = tmp_path / "dist"
    local.mkdir()
    content = b"<html>v2</html>"
    (local / "index.html").write_bytes(content)

    uploads: list[str] = []

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method: str, url: str, **kwargs):
            if "/access-key/whoami" in url:
                return httpx.Response(
                    200,
                    json={"account_id": "acc-1", "account_short_id": "acct"},
                )
            if method == "GET" and "/objects" in url and "multipart" not in url:
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {"key": "index.html", "size": len(content), "is_dir": False}
                        ],
                        "total": 1,
                        "pages": 1,
                        "page": 1,
                        "page_size": 100,
                    },
                )
            if method == "POST" and "/objects" in url:
                uploads.append(kwargs.get("data", {}).get("key", ""))
                return httpx.Response(201, json={"key": "index.html"})
            return httpx.Response(404)

    monkeypatch.setattr("homecloud_core.transport.httpx.Client", MockHttpClient)

    result = runner.invoke(
        app,
        ["so", "sync", str(local), "so://my-bucket/", "--output", "json"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert uploads == ["index.html"]
    summary = json.loads(result.stdout)
    assert summary["uploaded"] == 1
    assert summary["skipped"] == 0


def test_so_sync_skip_same_size_when_flag_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
) -> None:
    cred_file = tmp_path / "credentials"
    cred_file.write_text(
        json.dumps(
            {
                "version": 2,
                "default_profile": "default",
                "profiles": {
                    "default": {
                        "apex": "example.test",
                        "access_key_id": "HCAK1",
                        "secret_access_key": "secret",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOMECLOUD_CREDENTIALS_FILE", str(cred_file))
    monkeypatch.setenv("HOMECLOUD_CONFIG_DIR", str(tmp_path))

    local = tmp_path / "dist"
    local.mkdir()
    content = b"<html>same</html>"
    (local / "index.html").write_bytes(content)

    uploads: list[str] = []

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method: str, url: str, **kwargs):
            if "/access-key/whoami" in url:
                return httpx.Response(
                    200,
                    json={"account_id": "acc-1", "account_short_id": "acct"},
                )
            if method == "GET" and "/objects" in url and "multipart" not in url:
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {"key": "index.html", "size": len(content), "is_dir": False}
                        ],
                        "total": 1,
                        "pages": 1,
                        "page": 1,
                        "page_size": 100,
                    },
                )
            if method == "POST" and "/objects" in url:
                uploads.append(kwargs.get("data", {}).get("key", ""))
                return httpx.Response(201, json={"key": "index.html"})
            return httpx.Response(404)

    monkeypatch.setattr("homecloud_core.transport.httpx.Client", MockHttpClient)

    result = runner.invoke(
        app,
        ["so", "sync", str(local), "so://my-bucket/", "--skip", "--output", "json"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert uploads == []
    summary = json.loads(result.stdout)
    assert summary["uploaded"] == 0
    assert summary["skipped"] == 1


def test_so_sync_downloads_remote_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
) -> None:
    cred_file = tmp_path / "credentials"
    cred_file.write_text(
        json.dumps(
            {
                "version": 2,
                "default_profile": "default",
                "profiles": {
                    "default": {
                        "apex": "example.test",
                        "access_key_id": "HCAK1",
                        "secret_access_key": "secret",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOMECLOUD_CREDENTIALS_FILE", str(cred_file))
    monkeypatch.setenv("HOMECLOUD_CONFIG_DIR", str(tmp_path))

    local = tmp_path / "site"

    class MockStreamResponse:
        status_code = 200

        @property
        def is_success(self) -> bool:
            return True

        def iter_bytes(self, chunk_size: int = 1024) -> bytes:
            yield b"<html></html>"

        def read(self) -> bytes:
            return b""

        def close(self) -> None:
            return None

    class MockStreamContext:
        def __init__(self, response: MockStreamResponse):
            self._response = response

        def __enter__(self) -> MockStreamResponse:
            return self._response

        def __exit__(self, *args) -> bool:
            return False

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method: str, url: str, **kwargs):
            if "/access-key/whoami" in url:
                return httpx.Response(
                    200,
                    json={"account_id": "acc-1", "account_short_id": "acct"},
                )
            if method == "GET" and url.endswith("/objects") or (
                method == "GET" and "/objects?" in url
            ):
                return httpx.Response(
                    200,
                    json={
                        "items": [{"key": "index.html", "size": 13, "is_dir": False}],
                        "total": 1,
                        "pages": 1,
                        "page": 1,
                        "page_size": 100,
                    },
                )
            return httpx.Response(404)

        def stream(self, method: str, url: str, **kwargs):
            if method == "GET" and "/objects/index.html" in url:
                return MockStreamContext(MockStreamResponse())
            return MockStreamContext(
                type(
                    "Err",
                    (),
                    {
                        "status_code": 404,
                        "is_success": property(lambda self: False),
                        "iter_bytes": lambda self, chunk_size=1024: iter(()),
                        "read": lambda self: b"not found",
                        "close": lambda self: None,
                    },
                )()
            )

    monkeypatch.setattr("homecloud_core.transport.httpx.Client", MockHttpClient)

    result = runner.invoke(
        app,
        ["so", "sync", "so://docs/", str(local), "--output", "json"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert (local / "index.html").read_text(encoding="utf-8") == "<html></html>"


def test_so_sync_downloads_object_key_with_spaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
) -> None:
    cred_file = tmp_path / "credentials"
    cred_file.write_text(
        json.dumps(
            {
                "version": 2,
                "default_profile": "default",
                "profiles": {
                    "default": {
                        "apex": "example.test",
                        "access_key_id": "HCAK1",
                        "secret_access_key": "secret",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOMECLOUD_CREDENTIALS_FILE", str(cred_file))
    monkeypatch.setenv("HOMECLOUD_CONFIG_DIR", str(tmp_path))

    local = tmp_path / "local-dir"
    object_key = "watch/spider noir/1/file.mkv"
    downloaded_urls: list[str] = []

    class MockStreamResponse:
        status_code = 200

        @property
        def is_success(self) -> bool:
            return True

        def iter_bytes(self, chunk_size: int = 1024) -> bytes:
            yield b"video-bytes"

        def read(self) -> bytes:
            return b""

        def close(self) -> None:
            return None

    class MockStreamContext:
        def __init__(self, response: MockStreamResponse):
            self._response = response

        def __enter__(self) -> MockStreamResponse:
            return self._response

        def __exit__(self, *args) -> bool:
            return False

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method: str, url: str, **kwargs):
            if "/access-key/whoami" in url:
                return httpx.Response(
                    200,
                    json={"account_id": "acc-1", "account_short_id": "acct"},
                )
            if method == "GET" and "/objects/watch/spider%20noir/1/file.mkv/metadata" in url:
                return httpx.Response(
                    200,
                    json={"key": object_key, "size": 11, "metadata": {}, "tags": {}},
                )
            if method == "GET" and "/objects" in url and "multipart" not in url:
                return httpx.Response(
                    200,
                    json={
                        "items": [],
                        "total": 0,
                        "pages": 1,
                        "page": 1,
                        "page_size": 100,
                    },
                )
            return httpx.Response(404)

        def stream(self, method: str, url: str, **kwargs):
            downloaded_urls.append(url)
            if method == "GET" and "/objects/watch/spider%20noir/1/file.mkv" in url:
                return MockStreamContext(MockStreamResponse())
            return MockStreamContext(
                type(
                    "Err",
                    (),
                    {
                        "status_code": 404,
                        "is_success": property(lambda self: False),
                        "iter_bytes": lambda self, chunk_size=1024: iter(()),
                        "read": lambda self: b"not found",
                        "close": lambda self: None,
                    },
                )()
            )

    monkeypatch.setattr("homecloud_core.transport.httpx.Client", MockHttpClient)

    result = runner.invoke(
        app,
        [
            "so",
            "sync",
            f"so://my-bucket/{object_key}",
            str(local),
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert downloaded_urls
    assert "%20" in downloaded_urls[0]
    assert (local / "file.mkv").read_bytes() == b"video-bytes"
    summary = json.loads(result.stdout)
    assert summary["downloaded"] == 1


def test_so_sync_rejects_two_local_paths(
    runner: CliRunner,
) -> None:
    result = runner.invoke(app, ["so", "sync", "./a", "./b"])
    assert result.exit_code != 0
    assert "so://" in result.stderr or "so://" in result.stdout


def test_so_rm_recursive_deletes_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
) -> None:
    cred_file = tmp_path / "credentials"
    cred_file.write_text(
        json.dumps(
            {
                "version": 2,
                "default_profile": "default",
                "profiles": {
                    "default": {
                        "apex": "example.test",
                        "access_key_id": "HCAK1",
                        "secret_access_key": "secret",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOMECLOUD_CREDENTIALS_FILE", str(cred_file))
    monkeypatch.setenv("HOMECLOUD_CONFIG_DIR", str(tmp_path))

    deleted: list[str] = []

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method: str, url: str, **kwargs):
            if "/access-key/whoami" in url:
                return httpx.Response(
                    200,
                    json={"account_id": "acc-1", "account_short_id": "acct"},
                )
            if method == "GET" and "/objects" in url:
                return httpx.Response(
                    200,
                    json={
                        "items": [{"key": "a.txt", "size": 1, "is_dir": False}],
                        "total": 1,
                        "pages": 1,
                        "page": 1,
                        "page_size": 100,
                    },
                )
            if method == "DELETE":
                deleted.append(url)
                return httpx.Response(204)
            return httpx.Response(404)

    monkeypatch.setattr("homecloud_core.transport.httpx.Client", MockHttpClient)

    result = runner.invoke(app, ["so", "rm", "so://my-bucket/", "--recursive"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert len(deleted) == 1
    assert deleted[0].endswith("/objects/a.txt")


def test_inline_access_key_flags_without_credentials_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
) -> None:
    monkeypatch.setenv("HOMECLOUD_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("HOMECLOUD_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("HOMECLOUD_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("HOMECLOUD_SECRET_ACCESS_KEY", raising=False)

    class MockHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method: str, url: str, **kwargs):
            if "/access-key/whoami" in url:
                return httpx.Response(
                    200,
                    json={"account_id": "acc-1", "account_short_id": "acct"},
                )
            if method == "GET" and "/objects" in url:
                return httpx.Response(
                    200,
                    json={"items": [], "total": 0, "pages": 1, "page": 1, "page_size": 100},
                )
            return httpx.Response(404)

    monkeypatch.setattr("homecloud_core.transport.httpx.Client", MockHttpClient)

    result = runner.invoke(
        app,
        [
            "--access-key-id",
            "HCAKINLINE",
            "--secret-access-key",
            "inline-secret",
            "so",
            "ls",
            "my-bucket",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
