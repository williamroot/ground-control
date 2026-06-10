"""Helpers de token/secret do agente (Spec #1R-a) — sha256, constant-time.

Invariantes de segurança:
- new_enroll_token() → ('gcat_<rand>', sha256hex) ; plaintext só aqui.
- new_agent_secret() → ('gca_<rand>', sha256hex).
- hash_token determinístico.
- verify usa hmac.compare_digest; False para presented/stored vazios.
- NENHUM plaintext é igual ao hash (o hash é o que vai pro banco).
"""

from __future__ import annotations

import hashlib

from gerti_sidecar.domain.agent_secrets import (
    hash_token,
    new_agent_secret,
    new_enroll_token,
    verify,
)


def test_new_enroll_token_prefix_and_hash():
    plain, digest = new_enroll_token()
    assert plain.startswith("gcat_")
    assert digest == hashlib.sha256(plain.encode()).hexdigest()
    assert len(digest) == 64
    assert plain != digest


def test_new_agent_secret_prefix_and_hash():
    plain, digest = new_agent_secret()
    assert plain.startswith("gca_")
    assert digest == hashlib.sha256(plain.encode()).hexdigest()
    assert plain != digest


def test_tokens_are_unique():
    p1, _ = new_enroll_token()
    p2, _ = new_enroll_token()
    assert p1 != p2


def test_hash_token_deterministic():
    assert hash_token("hello") == hash_token("hello")
    assert hash_token("hello") != hash_token("world")
    assert hash_token("hello") == hashlib.sha256(b"hello").hexdigest()


def test_verify_constant_time_match():
    plain, digest = new_enroll_token()
    assert verify(plain, digest) is True
    assert verify(plain + "x", digest) is False


def test_verify_empty_inputs_false():
    _, digest = new_enroll_token()
    assert verify("", digest) is False
    assert verify("whatever", "") is False
    assert verify("", "") is False
