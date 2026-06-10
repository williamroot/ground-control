"""Bootstrap da aplicação FastAPI do sidecar.

Padrão factory + lifespan para que testes possam construir apps isoladas.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gerti_sidecar import __version__
from gerti_sidecar.config import get_settings
from gerti_sidecar.db import dispose_db, init_db
from gerti_sidecar.routers import (
    admin_agents,
    admin_ai,
    admin_analytics,
    admin_auth,
    admin_automation,
    admin_contracts,
    admin_invoices,
    admin_tenants,
    admin_timer,
    agent,
    assets,
    auth,
    branding,
    contracts,
    dashboard,
    health,
    hooks,
    invoices,
    me,
    ticketing_meta,
    tickets,
)

logger = logging.getLogger("gerti_sidecar")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    logger.info("starting sidecar (env=%s, version=%s)", settings.environment, __version__)
    init_db(settings)
    try:
        yield
    finally:
        logger.info("stopping sidecar")
        await dispose_db()


def create_app() -> FastAPI:
    from gerti_sidecar.middleware.tenant import TenantMiddleware

    settings = get_settings()
    app = FastAPI(
        title="Gerti Service Desk API",
        version=__version__,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        lifespan=lifespan,
    )

    app.include_router(health.router, prefix=settings.api_v1_prefix)
    app.include_router(branding.router, prefix=settings.api_v1_prefix)
    app.include_router(me.router, prefix=settings.api_v1_prefix)
    app.include_router(auth.router, prefix=settings.api_v1_prefix)
    app.include_router(contracts.router, prefix=settings.api_v1_prefix)
    app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
    app.include_router(ticketing_meta.router, prefix=settings.api_v1_prefix)
    app.include_router(tickets.router, prefix=settings.api_v1_prefix)
    app.include_router(assets.router, prefix=settings.api_v1_prefix)
    # Faturas internas (Spec #1P) — portal admin do tenant: lista/baixa PDF.
    app.include_router(invoices.router, prefix=settings.api_v1_prefix)
    # Console de Administração (Spec #1G-a) — cross-tenant, sessão gsid_adm.
    app.include_router(admin_auth.router, prefix=settings.api_v1_prefix)
    app.include_router(admin_tenants.router, prefix=settings.api_v1_prefix)
    app.include_router(admin_contracts.router, prefix=settings.api_v1_prefix)
    # Faturas internas — console gera/gerencia (Spec #1P).
    app.include_router(admin_invoices.router, prefix=settings.api_v1_prefix)
    # Time tracker do agente (Spec #1J).
    app.include_router(admin_timer.router, prefix=settings.api_v1_prefix)
    # IA: sumarização + resposta sugerida (Spec #1N) — opt-in.
    app.include_router(admin_ai.router, prefix=settings.api_v1_prefix)
    # Dashboards por tenant — console analytics (Spec #1O), cross-tenant.
    app.include_router(admin_analytics.router, prefix=settings.api_v1_prefix)
    # CRUD de regras de automação (Spec #1Q) — console, validação server-side.
    app.include_router(admin_automation.router, prefix=settings.api_v1_prefix)
    # Console de tokens/dispositivos do agente de inventário (Spec #1R-a).
    app.include_router(admin_agents.router, prefix=settings.api_v1_prefix)
    # Webhooks Znuny→sidecar (Spec #1Q) — tenant vem do customer_id assinado (HMAC).
    app.include_router(hooks.router, prefix=settings.api_v1_prefix)
    # Agente de inventário (Spec #1R-a) — Bearer token/secret; tenant vem do token.
    app.include_router(agent.router, prefix=settings.api_v1_prefix)
    app.add_middleware(TenantMiddleware)

    return app


# Para uvicorn rodar: `uvicorn gerti_sidecar.main:app`
app = create_app()
