"""Testes do claim `znuny_login` em SessionPayload (Spec #1F).

Cobre:
- encode_session sem znuny_login → decoded znuny_login == customer_login.
- encode_session com znuny_login explícito → decoded carrega ambos corretamente.
- Token legado (sem claim znuny_login) → decode faz fallback para customer_login.
"""

from __future__ import annotations

import datetime as dt

import jwt
import pytest

from gerti_sidecar.auth import session as sess
from gerti_sidecar.config import get_settings


@pytest.fixture(autouse=True)
def _use_test_secret(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()


def test_encode_no_znuny_login_defaults_to_customer_login():
    """encode_session sem znuny_login → znuny_login == customer_login."""
    st = get_settings()
    token = sess.encode_session("tid-1", "eduardo.salvi@aurora.com", "helpdesk", st)
    payload = sess.decode_session(token, st)
    assert payload is not None
    assert payload["customer_login"] == "eduardo.salvi@aurora.com"
    assert payload["znuny_login"] == "eduardo.salvi@aurora.com"


def test_encode_with_explicit_znuny_login():
    """encode_session com znuny_login explícito → decoded carrega ambos."""
    st = get_settings()
    token = sess.encode_session(
        "tid-2",
        "eduardo.salvi@aurora.com",
        "admin",
        st,
        znuny_login="eduardo.salvi",
    )
    payload = sess.decode_session(token, st)
    assert payload is not None
    assert payload["customer_login"] == "eduardo.salvi@aurora.com"
    assert payload["znuny_login"] == "eduardo.salvi"


def test_decode_legacy_token_missing_znuny_login_falls_back():
    """Token sem claim znuny_login (emitido antes do #1F) → fallback p/ customer_login."""
    st = get_settings()
    exp = int((dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)).timestamp())
    # Token legado: sem znuny_login, com role (pós-#1H).
    legacy = jwt.encode(
        {
            "tenant_id": "tid-3",
            "customer_login": "maria@technova.example",
            "role": "helpdesk",
            "exp": exp,
        },
        st.session_secret,
        algorithm="HS256",
    )
    payload = sess.decode_session(legacy, st)
    assert payload is not None
    assert payload["customer_login"] == "maria@technova.example"
    # Fallback: znuny_login == customer_login para tokens antigos.
    assert payload["znuny_login"] == "maria@technova.example"


def test_decode_token_with_non_str_znuny_login_falls_back():
    """Token com znuny_login de tipo errado → fallback p/ customer_login."""
    st = get_settings()
    exp = int((dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)).timestamp())
    malformed = jwt.encode(
        {
            "tenant_id": "tid-4",
            "customer_login": "x@y.com",
            "znuny_login": 12345,  # tipo errado
            "role": "helpdesk",
            "exp": exp,
        },
        st.session_secret,
        algorithm="HS256",
    )
    payload = sess.decode_session(malformed, st)
    assert payload is not None
    assert payload["znuny_login"] == "x@y.com"
