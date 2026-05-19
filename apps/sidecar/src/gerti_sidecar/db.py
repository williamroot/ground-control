"""Engine e session factory SQLAlchemy async para Postgres."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gerti_sidecar.config import Settings


def make_engine(settings: Settings) -> AsyncEngine:
    """Cria engine async com configurações sensatas para o ambiente."""
    return create_async_engine(
        str(settings.database_url),
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800,
    )


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Cria factory de sessions async ligada à engine."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# Variáveis de módulo populadas no lifespan da app (ver main.py).
# Testes podem substituir via fixture.
engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None
admin_engine: AsyncEngine | None = None
AdminSessionLocal: async_sessionmaker[AsyncSession] | None = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependência FastAPI: yielda uma sessão por request."""
    if SessionLocal is None:
        raise RuntimeError("DB não inicializado — chame init_db() no lifespan")
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Helper para scripts e jobs que não tem ciclo FastAPI."""
    if SessionLocal is None:
        raise RuntimeError("DB não inicializado")
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def init_db(settings: Settings) -> None:
    """Inicializa engine e session factory globais a partir das settings."""
    global engine, SessionLocal, admin_engine, AdminSessionLocal
    engine = make_engine(settings)
    SessionLocal = make_session_factory(engine)
    if settings.database_admin_url is not None:
        admin_engine = create_async_engine(
            str(settings.database_admin_url),
            echo=settings.debug,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=2,
            pool_recycle=1800,
        )
        AdminSessionLocal = make_session_factory(admin_engine)
    else:
        admin_engine = None
        AdminSessionLocal = None


async def dispose_db() -> None:
    """Fecha o pool de conexões; chamar no shutdown."""
    global engine, SessionLocal, admin_engine, AdminSessionLocal
    if engine is not None:
        await engine.dispose()
    if admin_engine is not None:
        await admin_engine.dispose()
    engine = None
    SessionLocal = None
    admin_engine = None
    AdminSessionLocal = None


@asynccontextmanager
async def tenant_session_scope(
    tenant_id: uuid.UUID,
    *,
    factory: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncIterator[AsyncSession]:
    """Yield a session with `app.current_tenant` set for the whole transaction.

    SET LOCAL is transaction-scoped, so we open an explicit transaction and
    set the GUC inside it before yielding. Commits on success, rolls back on
    error. `factory` overrides the module SessionLocal (tests/jobs).
    """
    sm = factory if factory is not None else SessionLocal
    if sm is None:
        raise RuntimeError("DB não inicializado — chame init_db() no lifespan")
    async with sm() as session:
        async with session.begin():
            # asyncpg não aceita bind params em `SET LOCAL`; set_config(..., true)
            # é o equivalente transaction-scoped e parametrizável (anti-injeção).
            await session.execute(
                text("SELECT set_config('app.current_tenant', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            yield session


async def get_tenant_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: tenant-scoped session for tenant-bound routes.

    Requires TenantMiddleware to have set request.state.tenant. Raises if
    absent (route is tenant-scoped but no tenant was resolved).
    """
    tenant = getattr(request.state, "tenant", None)
    if tenant is None:
        raise RuntimeError("get_tenant_session usado em rota sem tenant resolvido")
    async with tenant_session_scope(tenant.id) as session:
        yield session
