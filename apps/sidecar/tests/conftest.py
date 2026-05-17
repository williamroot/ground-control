"""Fixtures globais de testes.

Estratégia: cada sessão de pytest sobe um Postgres real via testcontainers,
roda o init script do infra/compose, aplica as migrations Alembic, e
fornece sessions isoladas por teste (rollback ao final).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from gerti_sidecar.config import get_settings
from gerti_sidecar.models import Tenant, ZnunyInstance

ROOT = Path(__file__).resolve().parents[1]
INIT_SQL = (
    ROOT.parent.parent / "infra" / "compose" / "postgres" / "init" / "001_schemas_and_roles.sql"
)


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Generator[None, None, None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    with PostgresContainer("postgres:18", driver="asyncpg") as pg:
        # roda init script
        import psycopg

        sync_url = pg.get_connection_url().replace("+asyncpg", "")
        with psycopg.connect(sync_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(INIT_SQL.read_text())
        yield pg


@pytest.fixture(scope="session")
def db_url(postgres_container: PostgresContainer) -> str:
    return postgres_container.get_connection_url()


@pytest.fixture
async def engine(db_url: str) -> AsyncGenerator:
    """Engine apontando para o testcontainer, com migrations aplicadas."""
    import os

    from alembic import command
    from alembic.config import Config

    eng = create_async_engine(db_url, echo=False, future=True)

    # roda migrations
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    os.environ["DATABASE_URL"] = db_url
    await asyncio.to_thread(command.upgrade, cfg, "head")

    yield eng

    # downgrade limpa tabelas
    await asyncio.to_thread(command.downgrade, cfg, "base")
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
        await s.rollback()


@pytest.fixture
def app_db_url(db_url: str) -> str:
    """Same DB as `db_url` but as the unprivileged gerti_sidecar role (RLS applies)."""
    # db_url is the testcontainers admin URL; swap user:pass to gerti_sidecar.
    after_at = db_url.split("@", 1)[1]
    return f"postgresql+asyncpg://gerti_sidecar:dev_change_me@{after_at}"


@pytest.fixture
async def app_session_factory(
    engine, app_db_url: str
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """async_sessionmaker bound to a gerti_sidecar (RLS-subject) engine.

    `engine` fixture has already applied Alembic head on the shared DB.
    """
    app_engine = create_async_engine(app_db_url, echo=False)
    factory = async_sessionmaker(app_engine, expire_on_commit=False)
    yield factory
    await app_engine.dispose()


@pytest.fixture
async def seed_two_tenants(session) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed two tenants via the admin session (bypasses RLS for setup)."""
    inst = ZnunyInstance(
        name="main",
        base_url="http://znuny",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    a = Tenant(
        legal_name="A SA",
        trade_name="A",
        document="1",
        znuny_customer_id="a",
        znuny_instance_id=inst.id,
        subdomain="a",
    )
    b = Tenant(
        legal_name="B SA",
        trade_name="B",
        document="2",
        znuny_customer_id="b",
        znuny_instance_id=inst.id,
        subdomain="b",
    )
    session.add_all([a, b])
    await session.commit()
    return a.id, b.id
