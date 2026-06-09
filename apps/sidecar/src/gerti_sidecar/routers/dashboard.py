"""GET /v1/dashboard — resumo + alertas de saldo baixo, read-only, tenant da sessão (RLS)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session, require_admin
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.consumption_service import ConsumptionService
from gerti_sidecar.domain.contract_read_service import ContractReadService
from gerti_sidecar.domain.metrics_service import MetricsService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import Contract, Tenant

# Spec #1H: dashboard expõe saldos/valores — admin-only (igual /contracts).
router = APIRouter(prefix="/dashboard", tags=["portal"], dependencies=[Depends(require_admin)])


class BalanceByType(BaseModel):
    type: str
    kind: str
    contract_count: int
    total_remaining: float | None


class LowBalanceAlertOut(BaseModel):
    contract_id: str
    code: str
    type: str
    kind: str
    remaining: float
    consumed_percent: float | None
    severity: str


class DashboardOut(BaseModel):
    contract_count: int
    balances_by_type: list[BalanceByType]
    low_balance_alerts: list[LowBalanceAlertOut]


@router.get("", response_model=DashboardOut)
async def get_dashboard(
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> DashboardOut:
    contracts = (await session.execute(select(Contract).order_by(Contract.code))).scalars().all()
    cons = ConsumptionService(session)
    reads = ContractReadService(session)

    counts: dict[str, int] = defaultdict(int)
    kinds: dict[str, str] = {}
    totals: dict[str, float | None] = {}
    alerts: list[LowBalanceAlertOut] = []
    for c in contracts:
        bal = await cons.balance(c.id)
        t = c.type.value
        counts[t] += 1
        kinds[t] = bal.kind
        if bal.remaining is None:
            totals[t] = None  # n/a stays None
        else:
            prev = totals.get(t)
            totals[t] = float(bal.remaining) if prev is None else prev + float(bal.remaining)
        alert = await reads.low_balance(c)
        if alert is not None:
            alerts.append(
                LowBalanceAlertOut(
                    contract_id=str(alert.contract_id),
                    code=alert.code,
                    type=alert.type,
                    kind=alert.kind,
                    remaining=alert.remaining,
                    consumed_percent=alert.consumed_percent,
                    severity=alert.severity,
                )
            )
    balances = [
        BalanceByType(
            type=t, kind=kinds[t], contract_count=counts[t], total_remaining=totals.get(t)
        )
        for t in sorted(counts)
    ]
    return DashboardOut(
        contract_count=len(contracts),
        balances_by_type=balances,
        low_balance_alerts=alerts,
    )


def _period_days(period: str) -> int:
    """Aceita 30d|90d (default 30d). Qualquer outro valor -> 30."""
    table = {"30d": 30, "90d": 90}
    return table.get(period, 30)


@router.get("/metrics")
async def get_dashboard_metrics(
    request: Request,
    period: str = "30d",
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> dict[str, Any]:
    """KPIs do dashboard (#1O) — admin do tenant (router-level require_admin).

    CSAT/horas/saldo do Postgres tenant-scoped (RLS via get_tenant_session);
    tickets/SLA via GI escopado pelo CustomerID do tenant da sessão. Failure-soft.
    """
    tenant: Tenant = request.state.tenant
    svc = MetricsService(session, znuny_ticket)
    return await svc.tenant_metrics(
        tenant_id=tenant.id,
        customer_id=tenant.znuny_customer_id,
        period_days=_period_days(period),
    )
