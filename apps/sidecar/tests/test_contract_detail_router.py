"""GET /v1/contracts/{id}: detail, cycles totals raw, adjustment/renewal/parties, 404 cross-tenant."""  # noqa: E501

from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import (
    Contract,
    ContractAdjustmentRule,
    ContractBillingParty,
    ContractCycle,
    ContractRenewalPolicy,
    Tenant,
    TenantBranding,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus


async def _two_tenants_with_contract(session):
    inst = ZnunyInstance(
        name="i",
        base_url="http://z",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    a = Tenant(
        legal_name="Aurora",
        trade_name="Aurora",
        document="1",
        znuny_customer_id="AURORA",
        znuny_instance_id=inst.id,
        subdomain="aurora",
    )
    b = Tenant(
        legal_name="Tech",
        trade_name="Tech",
        document="2",
        znuny_customer_id="TECH",
        znuny_instance_id=inst.id,
        subdomain="technova",
    )
    session.add_all([a, b])
    await session.flush()
    session.add_all(
        [
            TenantBranding(tenant_id=a.id, display_name="Aurora Móveis"),
            TenantBranding(tenant_id=b.id, display_name="TechNova"),
        ]
    )
    c = Contract(
        tenant_id=a.id,
        code="AUR-HB",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=40,
        unit_price_brl=180,
        created_by="seed",
    )
    session.add(c)
    await session.flush()
    closed = ContractCycle(
        contract_id=c.id,
        kind=CycleKind.closing,
        period_start=dt.date(2026, 1, 1),
        period_end=dt.date(2026, 1, 31),
        status=CycleStatus.closed,
        closed_at=dt.datetime(2026, 2, 1, tzinfo=dt.UTC),
        totals={"consumed_minutes": 360.0, "overage_minutes": 0.0, "event_count": 3},
    )
    open_billing = ContractCycle(
        contract_id=c.id,
        kind=CycleKind.billing,
        period_start=dt.date(2026, 2, 1),
        period_end=dt.date(2026, 2, 28),
        status=CycleStatus.open,
    )
    session.add_all([closed, open_billing])
    session.add(
        ContractAdjustmentRule(
            contract_id=c.id,
            index_code="IPCA",
            cadence_months=12,
            next_run_on=dt.date(2027, 1, 1),
            cap_percent=8.00,
        )
    )
    session.add(
        ContractRenewalPolicy(
            contract_id=c.id,
            auto_renew=True,
            notice_days=30,
            next_review_on=dt.date(2026, 11, 30),
            renewal_term_months=12,
        )
    )
    session.add(
        ContractBillingParty(
            contract_id=c.id,
            legal_name="Aurora SA",
            document="18.472.366/0001-90",
            fiscal_address={"city": "SP"},
            payment_method="boleto",
        )
    )
    await session.commit()
    return a, b, c


@pytest.mark.asyncio
async def test_detail_full_and_404_cross_tenant(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    a, b, c = await _two_tenants_with_contract(session)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    ha = {"host": "aurora.suporte.gerti.com.br"}
    ht = {"host": "technova.suporte.gerti.com.br"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as cl:
        cl.cookies.set("gsid", encode_session(str(a.id), "joe", st))
        r = await cl.get(f"/v1/contracts/{c.id}", headers=ha)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == "AUR-HB"
        assert body["initial_hours"] == 40.0
        assert body["saldo"]["kind"] == "hours"
        # cycles ordered by period_start asc, both kinds; totals raw on closed, null on open
        assert [cy["kind"] for cy in body["cycles"]] == ["closing", "billing"]
        assert body["cycles"][0]["totals"]["event_count"] == 3
        assert body["cycles"][1]["totals"] is None
        assert body["adjustment_rule"]["index_code"] == "IPCA"
        assert body["adjustment_rule"]["cap_percent"] == 8.0
        assert body["renewal_policy"]["auto_renew"] is True
        assert len(body["billing_parties"]) == 1
        assert body["billing_parties"][0]["payment_method"] == "boleto"
        # cross-tenant: TechNova session asking Aurora's contract id -> 404 (RLS hid it)
        cl.cookies.clear()
        cl.cookies.set("gsid", encode_session(str(b.id), "x", st))
        xr = await cl.get(f"/v1/contracts/{c.id}", headers=ht)
        assert xr.status_code == 404
