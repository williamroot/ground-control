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
    admin_audit,
    admin_auth,
    admin_automation,
    admin_branding,
    admin_catalog,
    admin_contracts,
    admin_invoices,
    admin_kb,
    admin_search,
    admin_system,
    admin_tenant_queues,
    admin_tenants,
    admin_timer,
    admin_znuny,
    admin_znuny_people,
    agent,
    agent_dist,
    asaas_hooks,
    assets,
    auth,
    branding,
    catalog,
    checkout,
    contracts,
    dashboard,
    health,
    hooks,
    invoices,
    kb,
    me,
    notifications,
    preferences,
    search,
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
    # Relacionamentos cliente↔fila (T-R5.2). Mesmo prefixo /admin/tenants,
    # router separado por depender da lista viva de filas do Znuny.
    app.include_router(admin_tenant_queues.router, prefix=settings.api_v1_prefix)
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
    # Contratação self-service (Spec #2) — público; pré-cadastro → paga → provisiona.
    app.include_router(checkout.router, prefix=settings.api_v1_prefix)
    # Webhook do Asaas (Spec #2) — auth por token; sob /v1/hooks (allowlist).
    app.include_router(asaas_hooks.router, prefix=settings.api_v1_prefix)
    # Agente de inventário (Spec #1R-a) — Bearer token/secret; tenant vem do token.
    app.include_router(agent.router, prefix=settings.api_v1_prefix)
    # Distribuição do binário/install.sh do agente (Spec #1R-b) — público, sem auth.
    app.include_router(agent_dist.router, prefix=settings.api_v1_prefix)
    # Notificações + preferências do cliente (Spec #3 V3) — portal, escopo por destinatário.
    app.include_router(notifications.router, prefix=settings.api_v1_prefix)
    app.include_router(preferences.router, prefix=settings.api_v1_prefix)
    # Base de Conhecimento (Spec #3 V1) — portal: lista/busca/detalhe públicos.
    app.include_router(kb.router, prefix=settings.api_v1_prefix)
    # Base de Conhecimento — console CRUD (Spec #3 V1), cross-tenant.
    app.include_router(admin_kb.router, prefix=settings.api_v1_prefix)
    # Catálogo de Serviços (Spec #3 V2) — portal: vitrine de itens ativos.
    app.include_router(catalog.router, prefix=settings.api_v1_prefix)
    # Catálogo de Serviços — console CRUD (Spec #3 V2), cross-tenant.
    app.include_router(admin_catalog.router, prefix=settings.api_v1_prefix)
    # Identidade visual editável (Spec #3 V4) — console, reusa tenant_branding.
    app.include_router(admin_branding.router, prefix=settings.api_v1_prefix)
    # Trilha de auditoria (Spec #3 V5) — console, cross-tenant, sem RLS.
    app.include_router(admin_audit.router, prefix=settings.api_v1_prefix)
    # Saúde do sistema (Spec #3 V6) — console, sondas com falha isolada.
    app.include_router(admin_system.router, prefix=settings.api_v1_prefix)
    # Busca federada (Spec #3 V6) — portal (tenant-scoped) e console (cross-tenant).
    app.include_router(search.router, prefix=settings.api_v1_prefix)
    app.include_router(admin_search.router, prefix=settings.api_v1_prefix)
    # Console como capa de administração do Znuny (Spec #4, Blocos A/B) — não
    # persiste config do Znuny, só lê/escreve ao vivo pelo GI + audita.
    app.include_router(admin_znuny.router, prefix=settings.api_v1_prefix)
    # Console como capa de administração do Znuny (Spec #4, Blocos C/D) —
    # agentes/grupos + calendário/jornada; idem, sem persistência local.
    app.include_router(admin_znuny_people.router, prefix=settings.api_v1_prefix)
    app.add_middleware(TenantMiddleware)

    return app


# Para uvicorn rodar: `uvicorn gerti_sidecar.main:app`
app = create_app()
