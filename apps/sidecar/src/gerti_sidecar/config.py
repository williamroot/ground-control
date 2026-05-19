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

    # portal session (Spec #1F-a) ------------------------------------
    session_secret: str = "dev-insecure-session-secret-change-me"
    session_cookie_name: str = "gsid"
    session_ttl_seconds: int = 28800  # 8h

    # admin DSN usado SÓ pela resolução subdomínio->tenant (BYPASSRLS,
    # somente identidade — ver D16). Opcional: ausente => cai no
    # SessionLocal normal (dev/test ligam SessionLocal ao admin engine).
    database_admin_url: PostgresDsn | None = None

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

    @field_validator("database_admin_url")
    @classmethod
    def admin_must_be_async_dsn(cls, v: PostgresDsn | None) -> PostgresDsn | None:
        if v is None:
            return v
        scheme = str(v).split(":", 1)[0]
        if scheme != "postgresql+asyncpg":
            raise ValueError(
                f"database_admin_url deve usar driver asyncpg (got {scheme}); "
                "use 'postgresql+asyncpg://...'"
            )
        return v

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def session_cookie_secure(self) -> bool:
        # Plain-HTTP test/dev clients drop Secure cookies (H4).
        return self.environment not in ("development", "test")


@lru_cache
def get_settings() -> Settings:
    """Instância em cache (lru_cache) lida do ambiente. Importar via dependência do FastAPI."""
    return Settings()  # type: ignore[call-arg]
