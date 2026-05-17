"""Middleware que resolve tenant a partir do subdomínio do Host header.

Regras:
- Endpoints `/v1/health`, `/v1/openapi.json`, `/v1/docs`, `/v1/redoc` são meta:
  toleram ausência de tenant (não exige nem resolve).
- Hosts sem subdomínio (api.gerti.com.br, localhost) → request segue sem tenant.
- Subdomínio que mapeia para tenant existente → ativa app.current_tenant.
- Subdomínio que não mapeia → 404.

Após a Spec #1D (Auth Bridge), o claim `tenant_id` do JWT terá precedência sobre
o subdomínio; aqui ainda é resolução só por host porque o JWT vem depois.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Final

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from gerti_sidecar import db
from gerti_sidecar.models import Tenant

META_PATHS: Final[set[str]] = {
    "/v1/health",
    "/v1/openapi.json",
    "/v1/docs",
    "/v1/redoc",
}

# Hosts que nunca têm subdomínio de tenant (entry-points administrativos).
ROOT_HOSTS: Final[set[str]] = {
    "api.gerti.com.br",
    "localhost",
    "127.0.0.1",
    "testserver",  # padrão do httpx
}

SUBDOMAIN_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<sub>[a-z0-9][a-z0-9-]{0,62})\.suporte\.gerti\.com\.br$"
)


def extract_subdomain(host: str) -> str | None:
    """Extrai `acme` de `acme.suporte.gerti.com.br`. Retorna None se não casa."""
    host = host.split(":", 1)[0].lower()
    if host in ROOT_HOSTS:
        return None
    m = SUBDOMAIN_RE.match(host)
    return m.group("sub") if m else None


class TenantMiddleware(BaseHTTPMiddleware):
    """Resolve tenant via subdomínio e popula request.state.tenant."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # endpoints meta passam direto
        if request.url.path in META_PATHS:
            return await call_next(request)

        host = request.headers.get("host", "")
        subdomain = extract_subdomain(host)
        if subdomain is None:
            return await call_next(request)

        if db.SessionLocal is None:
            raise RuntimeError("DB não inicializado")

        async with db.SessionLocal() as session:
            result = await session.execute(
                select(Tenant).where(Tenant.subdomain == subdomain, Tenant.status == "active")
            )
            tenant = result.scalar_one_or_none()
            if tenant is None:
                # BaseHTTPMiddleware não roteia HTTPException pelos exception
                # handlers do FastAPI; retornamos a resposta diretamente.
                return JSONResponse(
                    status_code=404,
                    content={
                        "detail": {
                            "code": "tenant_not_found",
                            "subdomain": subdomain,
                        }
                    },
                )

            # Disponibiliza no request.state
            request.state.tenant = tenant

            response = await call_next(request)
            response.headers["x-gerti-tenant"] = str(tenant.id)
            return response
