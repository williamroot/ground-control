"""RLS deve impedir que sessão de tenant A leia linha de tenant B."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gerti_sidecar.models import Tenant, ZnunyInstance


@pytest.fixture
async def app_engine(db_url: str):
    """Engine conectada como gerti_sidecar (sujeita a RLS), não como superuser."""
    # db_url do testcontainer usa user 'test'; criamos engine apontando para
    # gerti_sidecar após migrations aplicadas pelo fixture engine padrão.
    parts = db_url.replace("postgresql+asyncpg://", "").split("@", 1)
    host_part = parts[1]
    app_url = f"postgresql+asyncpg://gerti_sidecar:dev_change_me@{host_part}"
    eng = create_async_engine(app_url, echo=False)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_read(engine, app_engine) -> None:
    # 1) Seed: 2 tenants via engine admin (sem RLS aplicado a superuser).
    factory_admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory_admin() as s:
        inst = ZnunyInstance(
            name="main",
            base_url="x",
            db_dsn_secret_ref="x",
            webservice_token_secret_ref="x",
            webhook_signing_secret_ref="x",
            mode="pool",
        )
        s.add(inst)
        await s.flush()
        a = Tenant(
            legal_name="A",
            trade_name="A",
            document="1",
            znuny_customer_id="acme",
            znuny_instance_id=inst.id,
            subdomain="acme",
        )
        b = Tenant(
            legal_name="B",
            trade_name="B",
            document="2",
            znuny_customer_id="beta",
            znuny_instance_id=inst.id,
            subdomain="beta",
        )
        s.add_all([a, b])
        await s.commit()
        a_id, b_id = a.id, b.id

    # 2) Sessão com role app_role + tenant A: deve ver só A.
    factory_app = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory_app() as s:
        await s.execute(text(f"SET LOCAL app.current_tenant = '{a_id}'"))
        result = await s.execute(text("SELECT id FROM gerti.tenant"))
        ids = {row[0] for row in result.all()}
    assert ids == {a_id}

    # 3) Mesma engine + tenant B: deve ver só B.
    async with factory_app() as s:
        await s.execute(text(f"SET LOCAL app.current_tenant = '{b_id}'"))
        result = await s.execute(text("SELECT id FROM gerti.tenant"))
        ids = {row[0] for row in result.all()}
    assert ids == {b_id}
