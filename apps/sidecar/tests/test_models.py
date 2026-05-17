"""Modelos básicos: znuny_instance e tenant."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.models import Tenant, ZnunyInstance


@pytest.mark.asyncio
async def test_can_create_znuny_instance(session: AsyncSession) -> None:
    inst = ZnunyInstance(
        name="main",
        base_url="http://znuny:80",
        db_dsn_secret_ref="vault:znuny/dsn",
        webservice_token_secret_ref="vault:znuny/token",
        webhook_signing_secret_ref="vault:znuny/webhook",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    assert inst.id is not None
    assert inst.status == "active"


@pytest.mark.asyncio
async def test_can_create_tenant(session: AsyncSession) -> None:
    inst = ZnunyInstance(
        name="main",
        base_url="http://znuny:80",
        db_dsn_secret_ref="vault:znuny/dsn",
        webservice_token_secret_ref="vault:znuny/token",
        webhook_signing_secret_ref="vault:znuny/webhook",
        mode="pool",
    )
    session.add(inst)
    await session.flush()

    t = Tenant(
        legal_name="Acme S.A.",
        trade_name="Acme",
        document="11.222.333/0001-44",
        znuny_customer_id="acme",
        znuny_instance_id=inst.id,
        subdomain="acme",
    )
    session.add(t)
    await session.flush()
    assert t.id is not None
    assert t.status == "active"


@pytest.mark.asyncio
async def test_tenant_subdomain_is_unique(session: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    inst = ZnunyInstance(
        name="main",
        base_url="http://znuny:80",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()

    t1 = Tenant(
        legal_name="A",
        trade_name="A",
        document="1",
        znuny_customer_id="a1",
        znuny_instance_id=inst.id,
        subdomain="dup",
    )
    t2 = Tenant(
        legal_name="B",
        trade_name="B",
        document="2",
        znuny_customer_id="b1",
        znuny_instance_id=inst.id,
        subdomain="dup",
    )
    session.add_all([t1, t2])
    with pytest.raises(IntegrityError):
        await session.flush()
