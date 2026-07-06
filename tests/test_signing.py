from homecloud_cli.signing import build_string_to_sign, compute_signature, sign_request_headers


def test_signature_matches_data_plane_format() -> None:
    string_to_sign = build_string_to_sign(
        method="GET",
        path="/acc-id/my-queue/messages",
        timestamp="2026-07-06T12:00:00Z",
        account_id="acc-id",
    )
    assert string_to_sign == "GET\n/acc-id/my-queue/messages\n2026-07-06T12:00:00Z\nacc-id"

    signature = compute_signature(secret="top-secret", string_to_sign=string_to_sign)
    assert len(signature) == 64


def test_sign_request_headers() -> None:
    headers = sign_request_headers(
        access_key_id="HCAKTEST",
        secret="top-secret",
        method="POST",
        path="/acc-id/q/messages",
        account_id="acc-id",
    )
    assert headers["X-Homecloud-Access-Key-Id"] == "HCAKTEST"
    assert headers["X-Homecloud-Date"].endswith("Z")
    assert len(headers["X-Homecloud-Signature"]) == 64
