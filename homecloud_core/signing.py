"""HomeCloud request signing (SigV1) — internal only."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone


def build_string_to_sign(
    *,
    method: str,
    path: str,
    timestamp: str,
    account_id: str,
) -> str:
    return f"{method.upper()}\n{path}\n{timestamp}\n{account_id}"


def compute_signature(*, secret: str, string_to_sign: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def sign_request_headers(
    *,
    access_key_id: str,
    secret: str,
    method: str,
    path: str,
    account_id: str,
    timestamp: datetime | None = None,
) -> dict[str, str]:
    ts = (timestamp or datetime.now(timezone.utc)).replace(microsecond=0)
    ts_str = ts.isoformat().replace("+00:00", "Z")
    string_to_sign = build_string_to_sign(
        method=method,
        path=path,
        timestamp=ts_str,
        account_id=account_id,
    )
    signature = compute_signature(secret=secret, string_to_sign=string_to_sign)
    return {
        "X-Homecloud-Access-Key-Id": access_key_id,
        "X-Homecloud-Date": ts_str,
        "X-Homecloud-Signature": signature,
    }
