"""Configuração centralizada do sidecar via pydantic-settings.

Todas as variáveis vêm de env (12-factor). Em dev, .env é carregado
automaticamente; em prod, secrets vêm do Vault e são exportadas como
env vars antes do processo iniciar.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]

_DEFAULT_SESSION_SECRET = "dev-insecure-session-secret-change-me"


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
    session_secret: str = _DEFAULT_SESSION_SECRET
    session_cookie_name: str = "gsid"
    session_ttl_seconds: int = 28800  # 8h

    # admin console session (Spec #1G-a) — cookie PRÓPRIO, nunca colide com o
    # `gsid` do cliente. Sessão de agente Znuny (role gerti_staff), cross-tenant.
    admin_session_cookie_name: str = "gsid_adm"

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

    @model_validator(mode="after")
    def _session_secret_set_in_prod(self) -> Settings:
        # Spec #1H: o papel (admin/helpdesk) viaja como claim assinado HS256 no
        # JWT. Um secret default/conhecido em prod permitiria forjar role=admin
        # → fail-closed: não sobe em production/staging sem um secret real.
        if self.environment in ("production", "staging") and (
            self.session_secret == _DEFAULT_SESSION_SECRET or not self.session_secret
        ):
            raise ValueError("SESSION_SECRET deve ser definido (não-default) em production/staging")
        return self

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
