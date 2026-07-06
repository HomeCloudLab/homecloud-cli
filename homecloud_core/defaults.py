"""Platform endpoint defaults — hidden from end users."""

from __future__ import annotations

import os

DEFAULT_APEX = "holab.abrdns.com"
DEFAULT_PROFILE = "default"


def platform_apex() -> str:
    return os.environ.get("HOMECLOUD_APEX", DEFAULT_APEX).strip().rstrip("/")


def console_url(apex: str | None = None) -> str:
    host = apex or platform_apex()
    return f"https://console.{host}/api/v1"


def mq_url(apex: str | None = None) -> str:
    host = apex or platform_apex()
    return f"https://mq.{host}"


def so_url(apex: str | None = None) -> str:
    host = apex or platform_apex()
    return f"https://so.{host}"


def secrets_url(apex: str | None = None) -> str:
    host = apex or platform_apex()
    return f"https://secrets.{host}"
