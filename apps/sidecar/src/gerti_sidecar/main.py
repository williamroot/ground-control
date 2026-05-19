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
from gerti_sidecar.routers import auth, branding, health, me

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
    app.add_middleware(TenantMiddleware)

    return app


# Para uvicorn rodar: `uvicorn gerti_sidecar.main:app`
app = create_app()
