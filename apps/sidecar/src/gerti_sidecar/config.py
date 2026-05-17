"""Configuração centralizada do sidecar via pydantic-settings.

Todas as variáveis vêm de env (12-factor). Em dev, .env é carregado
automaticamente; em prod, secrets vêm do Vault e são exportadas como
env vars antes do processo iniciar.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ambiente ---------------------------------------------------------
    environment: Environment = "development"
    debug: bool = False
    api_v1_prefix: str = "/v1"

    # banco ------------------------------------------------------------
    database_url: PostgresDsn

    # logging ----------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url")
    @classmethod
    def must_be_async_dsn(cls, v: PostgresDsn) -> PostgresDsn:
        scheme = str(v).split(":", 1)[0]
        if scheme != "postgresql+asyncpg":
            raise ValueError(
                f"database_url deve usar driver asyncpg (got {scheme}); "
                "use 'postgresql+asyncpg://...'"
            )
        return v

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"


@lru_cache
def get_settings() -> Settings:
    """Instância em cache (lru_cache) lida do ambiente. Importar via dependência do FastAPI."""
    return Settings()  # type: ignore[call-arg]
