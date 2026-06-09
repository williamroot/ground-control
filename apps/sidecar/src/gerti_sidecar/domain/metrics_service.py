"""MetricsService (Spec #1O): agrega os KPIs do dashboard por tenant.

Fontes:
  - CSAT: SELECT avg/count/histograma de gerti.csat_response (tenant-scoped, RLS).
  - Horas: soma de billable_minutes (consumo de trabalho) no período -> horas
    (tenant-scoped via RLS; representa o tempo de agente lançado nos contratos
    do tenant — alimentado pelo timer #1J via #1B).
  - Saldo/consumo: ContractReadService (#1B/#1F-b) — NÃO reimplementa a regra S3.
  - Tickets/SLA: GI ticket_stats(customer_id, since, until) — escopado por
    CustomerID (anti-IDOR no Perl).

Failure-soft: se o GI falhar (ZnunyUnavailable/ZnunyWriteError), o bloco
`tickets` degrada para None e o dashboard ainda renderiza o resto.

Opera sob uma sessão tenant-scoped (RLS): o caller abre tenant_session_scope.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.consumption_service import ConsumptionService
from gerti_sidecar.domain.contract_read_service import (
    ContractReadService,
    not_written_off_predicate,
)
from gerti_sidecar.integrations.znuny_ticket import (
    ZnunyUnavailable,
    ZnunyWriteError,
)
from gerti_sidecar.models import ConsumptionEvent, Contract, CsatResponse

__all__ = ["MetricsService"]


def _znuny_ts(value: dt.datetime) -> str:
    """Formata um datetime UTC no timestamp Znuny 'YYYY-MM-DD HH:MM:SS'."""
    return value.strftime("%Y-%m-%d %H:%M:%S")


class MetricsService:
    def __init__(self, session: AsyncSession, gi: Any) -> None:
        self._session = session
        self._gi = gi

    async def tenant_metrics(
        self,
        *,
        tenant_id: uuid.UUID,
        customer_id: str,
        period_days: int = 30,
    ) -> dict[str, Any]:
        now = dt.datetime.now(dt.UTC)
        since = now - dt.timedelta(days=period_days)

        csat = await self._csat(tenant_id)
        hours = await self._hours(since)
        balance = await self._balance()
        tickets = await self._tickets(customer_id, since, now)

        return {
            "period_days": period_days,
            "tickets": tickets,
            "csat": csat,
            "hours": hours,
            "balance": balance,
        }

    async def _csat(self, tenant_id: uuid.UUID) -> dict[str, Any]:
        """avg + count + histograma 1..5, da tabela tenant-scoped (RLS)."""
        row = (
            await self._session.execute(
                select(
                    func.avg(cast(CsatResponse.score, Integer)),
                    func.count(),
                ).where(CsatResponse.tenant_id == tenant_id)
            )
        ).one()
        avg = float(row[0]) if row[0] is not None else None
        count = int(row[1] or 0)

        dist_rows = (
            await self._session.execute(
                select(CsatResponse.score, func.count())
                .where(CsatResponse.tenant_id == tenant_id)
                .group_by(CsatResponse.score)
            )
        ).all()
        distribution = {s: 0 for s in range(1, 6)}
        for score, n in dist_rows:
            distribution[int(score)] = int(n)

        return {"avg": avg, "count": count, "distribution": distribution}

    async def _hours(self, since: dt.datetime) -> dict[str, Any]:
        """Soma de billable_minutes (não-glosado) no período -> horas.

        Tenant-scoped via RLS (a sessão tem app.current_tenant). Representa o
        tempo de agente lançado nos contratos deste tenant (timer #1J -> #1B).
        """
        total_minutes = (
            await self._session.execute(
                select(func.coalesce(func.sum(ConsumptionEvent.billable_minutes), 0)).where(
                    ConsumptionEvent.occurred_at >= since,
                    not_written_off_predicate(),
                )
            )
        ).scalar_one()
        minutes = float(total_minutes or 0.0)
        return {"total_minutes": minutes, "total_hours": round(minutes / 60.0, 2)}

    async def _balance(self) -> dict[str, Any]:
        """Contagem de contratos + saldo total por contrato + alertas (#1F-b)."""
        contracts = (
            (await self._session.execute(select(Contract).order_by(Contract.code))).scalars().all()
        )
        cons = ConsumptionService(self._session)
        reads = ContractReadService(self._session)

        per_contract: list[dict[str, Any]] = []
        alerts: list[dict[str, Any]] = []
        for c in contracts:
            bal = await cons.balance(c.id)
            per_contract.append(
                {
                    "contract_id": str(c.id),
                    "code": c.code,
                    "type": c.type.value,
                    "kind": bal.kind,
                    "remaining": float(bal.remaining) if bal.remaining is not None else None,
                    "consumed_percent": await reads.consumed_percent(c),
                }
            )
            alert = await reads.low_balance(c)
            if alert is not None:
                alerts.append(
                    {
                        "contract_id": str(alert.contract_id),
                        "code": alert.code,
                        "type": alert.type,
                        "kind": alert.kind,
                        "remaining": alert.remaining,
                        "consumed_percent": alert.consumed_percent,
                        "severity": alert.severity,
                    }
                )
        return {
            "contract_count": len(contracts),
            "contracts": per_contract,
            "low_balance_alerts": alerts,
        }

    async def _tickets(
        self, customer_id: str, since: dt.datetime, until: dt.datetime
    ) -> dict[str, Any] | None:
        """Tickets/SLA via GI. Failure-soft: GI fora do ar -> None."""
        try:
            stats = await self._gi.ticket_stats(
                customer_id=customer_id,
                since=_znuny_ts(since),
                until=_znuny_ts(until),
            )
        except (ZnunyUnavailable, ZnunyWriteError):
            return None
        return {
            "by_state": stats.by_state,
            "by_priority": stats.by_priority,
            "by_day": stats.by_day,
            "sla_breached": stats.sla_breached,
            "sla_at_risk": stats.sla_at_risk,
            "total": stats.total,
        }
