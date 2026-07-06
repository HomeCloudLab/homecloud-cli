from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from homecloud_cli.config import (
    CredentialsFile,
    Profile,
    load_credentials,
    save_credentials,
    upsert_profile,
)


def test_load_flat_ui_format(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cred_file = tmp_path / "credentials"
    cred_file.write_text(
        json.dumps(
            {
                "version": 1,
                "access_key_id": "HCAKTEST",
                "secret_access_key": "secret",
                "default_account_id": "acc-1",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOMECLOUD_CREDENTIALS_FILE", str(cred_file))

    credentials = load_credentials()
    profile = credentials.get_profile()
    assert profile.access_key_id == "HCAKTEST"
    assert profile.default_account_id == "acc-1"


def test_save_and_reload_multi_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cred_file = tmp_path / "credentials"
    monkeypatch.setenv("HOMECLOUD_CREDENTIALS_FILE", str(cred_file))

    credentials = CredentialsFile(
        version=1,
        default_profile="prod",
        profiles={
            "prod": Profile(
                name="prod",
                default_account_id="acc-prod",
                access_key_id="HCAKPROD",
                secret_access_key="secret-prod",
            )
        },
    )
    save_credentials(credentials)

    reloaded = load_credentials()
    profile = reloaded.get_profile("prod")
    assert profile.access_key_id == "HCAKPROD"
    if sys.platform != "win32":
        assert cred_file.stat().st_mode & 0o777 == 0o600


def test_upsert_profile_creates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cred_file = tmp_path / "credentials"
    monkeypatch.setenv("HOMECLOUD_CREDENTIALS_FILE", str(cred_file))

    upsert_profile(
        Profile(
            name="default",
            default_account_id="acc-1",
            access_key_id="HCAK1",
            secret_access_key="secret",
        )
    )

    credentials = load_credentials()
    assert credentials.default_profile == "default"
