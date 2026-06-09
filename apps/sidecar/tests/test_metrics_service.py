"""MetricsService (#1O): agrega CSAT (tabela tenant-scoped), horas, saldo
(via ContractReadService) e tickets/SLA (via GI ticket_stats). Failure-soft:
GI fora do ar -> bloco tickets=None, resto renderiza.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.metrics_service import MetricsService
from gerti_sidecar.integrations.znuny_ticket import TicketStats, ZnunyUnavailable
from gerti_sidecar.models import (
    Contract,
    CsatResponse,
    Tenant,
    TenantBranding,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType


async def _seed_tenant(session) -> uuid.UUID:
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
    session.add(a)
    await session.flush()
    session.add(TenantBranding(tenant_id=a.id, display_name="A"))
    hb = Contract(
        tenant_id=a.id,
        code="HB",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=10,
        unit_price_brl=100,
        created_by="seed",
    )
    session.add(hb)
    await session.flush()
    # CSAT: scores 5, 5, 3 -> avg 4.333..., count 3
    for sc, tid in ((5, 11), (5, 12), (3, 13)):
        session.add(
            CsatResponse(
                tenant_id=a.id,
                znuny_ticket_id=tid,
                customer_login="joe",
                score=sc,
            )
        )
    await session.commit()
    return a.id


class _FakeGI:
    def __init__(self, stats=None, fail=False):
        self._stats = stats
        self._fail = fail

    async def ticket_stats(self, *, customer_id, since, until):
        if self._fail:
            raise ZnunyUnavailable("down")
        assert customer_id == "AURORA"
        return self._stats


@pytest.mark.asyncio
async def test_tenant_metrics_aggregates(engine, app_session_factory, session, monkeypatch):
    tenant_id = await _seed_tenant(session)
    stats = TicketStats(
        by_state={"open": 3, "closed": 7},
        by_priority={"3 normal": 8},
        by_day=[{"date": "2026-06-01", "count": 4}],
        sla_breached=2,
        sla_at_risk=1,
        total=10,
    )
    gi = _FakeGI(stats=stats)
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = MetricsService(s, gi)
        out = await svc.tenant_metrics(tenant_id=tenant_id, customer_id="AURORA", period_days=30)
    # CSAT computed FROM the tenant-scoped table (RLS).
    assert out["csat"]["count"] == 3
    assert out["csat"]["avg"] == pytest.approx(4.3333, abs=1e-3)
    assert out["csat"]["distribution"][5] == 2
    assert out["csat"]["distribution"][3] == 1
    # Tickets/SLA from GI.
    assert out["tickets"]["by_state"] == {"open": 3, "closed": 7}
    assert out["tickets"]["sla_breached"] == 2
    assert out["tickets"]["by_day"] == [{"date": "2026-06-01", "count": 4}]
    # Balance via ContractReadService.
    assert out["balance"]["contract_count"] == 1
    # Hours block present.
    assert "hours" in out


@pytest.mark.asyncio
async def test_tenant_metrics_failure_soft_when_gi_down(
    engine, app_session_factory, session, monkeypatch
):
    tenant_id = await _seed_tenant(session)
    gi = _FakeGI(fail=True)
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = MetricsService(s, gi)
        out = await svc.tenant_metrics(tenant_id=tenant_id, customer_id="AURORA", period_days=30)
    # GI down -> tickets degrades to None; the rest still renders.
    assert out["tickets"] is None
    assert out["csat"]["count"] == 3
    assert out["balance"]["contract_count"] == 1
