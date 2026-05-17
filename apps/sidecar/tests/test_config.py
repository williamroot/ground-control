"""Settings devem carregar de env vars e validar tipos."""

import pytest
from pydantic import ValidationError

from gerti_sidecar.config import Settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host:5432/db")
    monkeypatch.setenv("ENVIRONMENT", "development")
    s = Settings()
    assert s.environment == "development"
    assert str(s.database_url) == "postgresql+asyncpg://u:p@host:5432/db"
    assert s.is_dev is True


def test_settings_rejects_invalid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host:5432/db")
    monkeypatch.setenv("ENVIRONMENT", "banana")
    with pytest.raises(ValidationError):
        Settings()


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host:5432/db")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    s = Settings()
    assert s.environment == "development"
    assert s.api_v1_prefix == "/v1"
