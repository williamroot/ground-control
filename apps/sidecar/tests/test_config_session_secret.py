"""Spec #1H (hardening): em production/staging o SESSION_SECRET não pode ser o
default (o papel viaja como claim assinado no JWT — secret conhecido = forjar admin).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from gerti_sidecar.config import Settings

_DSN = "postgresql+asyncpg://u:p@h/db"


def test_default_secret_rejected_in_production(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(environment="production", database_url=_DSN)  # type: ignore[call-arg]


def test_real_secret_ok_in_production():
    s = Settings(
        environment="production",
        database_url=_DSN,
        session_secret="a-real-strong-secret-value",  # type: ignore[call-arg]
    )
    assert s.session_secret == "a-real-strong-secret-value"


def test_default_secret_ok_in_dev_and_test():
    for env in ("development", "test"):
        s = Settings(environment=env, database_url=_DSN)  # type: ignore[call-arg]
        assert s.session_secret  # default permitido fora de prod/staging
