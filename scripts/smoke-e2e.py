#!/usr/bin/env python3
"""End-to-end smoke: MQ send/receive + SO upload/list/delete via HomeCloudClient.

Usage:
  export HOMECLOUD_ACCESS_KEY_ID=HCAK...
  export HOMECLOUD_SECRET_ACCESS_KEY=...
  export HOMECLOUD_ACCOUNT_ID=<uuid>   # optional if set in credentials
  export HOMECLOUD_QUEUE=test123
  export HOMECLOUD_SO_BUCKET=media
  python scripts/smoke-e2e.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import uuid

from homecloud_sdk import HomeCloudClient


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def main() -> int:
    queue = _env("HOMECLOUD_QUEUE", "test123")
    bucket = _env("HOMECLOUD_SO_BUCKET", "media")
    client = HomeCloudClient()

    print("=== MQ send/receive ===")
    tag = uuid.uuid4().hex[:8]
    sent = client.mq.send(queue, {"smoke": tag})
    print("send ok", sent.get("message_id") or sent.get("sequence") or sent)

    received = client.mq.receive(queue, max_messages=1, wait_seconds=10)
    if not received:
        print("MQ receive: no messages", file=sys.stderr)
        return 1
    print("receive ok", len(received), "message(s)")

    print("=== SO upload/list/delete ===")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tmp:
        tmp.write(f"cli-smoke-{tag}")
        tmp_path = tmp.name

    object_key = f"_smoke/cli-{tag}.txt"
    try:
        uploaded = client.storage.upload(bucket, tmp_path, key=object_key)
        print("upload ok", uploaded.get("key", object_key))

        listing = client.storage.list_objects(bucket, prefix=object_key)
        keys = [item.get("key") for item in listing.get("items", [])]
        if object_key not in keys:
            print(f"list missing {object_key!r}", file=sys.stderr)
            return 1
        print("list ok", object_key)

        client.storage.delete(bucket, object_key)
        print("delete ok", object_key)
    finally:
        os.unlink(tmp_path)

    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
