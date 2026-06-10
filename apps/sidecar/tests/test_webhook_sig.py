from __future__ import annotations

import hashlib
import hmac

from gerti_sidecar.integrations.webhook_sig import sign, verify

SECRET = "s3cr3t-shared-hmac-key"


def test_sign_verify_roundtrip():
    body = b'{"event":"ticket_create","ticket_id":1}'
    header = sign(SECRET, body)
    assert header.startswith("sha256=")
    assert verify(SECRET, body, header) is True


def test_tampered_body_fails():
    body = b'{"event":"ticket_create","ticket_id":1}'
    header = sign(SECRET, body)
    assert verify(SECRET, b'{"event":"ticket_create","ticket_id":2}', header) is False


def test_wrong_secret_fails():
    body = b"payload"
    header = sign(SECRET, body)
    assert verify("other-secret", body, header) is False


def test_accepts_bare_hex_and_prefixed():
    body = b"payload"
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert verify(SECRET, body, digest) is True
    assert verify(SECRET, body, f"sha256={digest}") is True


def test_missing_or_garbage_header_fails():
    assert verify(SECRET, b"x", "") is False
    assert verify(SECRET, b"x", "not-a-sig") is False
    assert verify("", b"x", "sha256=deadbeef") is False
