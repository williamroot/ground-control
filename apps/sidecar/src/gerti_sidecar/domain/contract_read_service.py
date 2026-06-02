"""Read-only views over the #1C contract domain for the portal (#1F-b).

ZERO writes: only select(...)/session.get(...) and ConsumptionService.balance.
The S3 approved-glosa rule lives HERE (and in ConsumptionService.balance) and
NOWHERE else — routers must reuse not_written_off_predicate() instead of
re-deriving it (avoids the `NULL NOT IN (..)` footgun).
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from gerti_sidecar.domain.consumption_service import Balance, ConsumptionService
from gerti_sidecar.models import ConsumptionEvent, Contract, Glosa
from gerti_sidecar.models.enums import ContractType, GlosaStatus


def not_written_off_predicate() -> ColumnElement[bool]:
    """The S3 rule: event counts toward balance iff no glosa OR glosa != approved.

    IDENTICAL to ConsumptionService.balance() (consumption_service.py). The
    explicit `glosa_id IS NULL` arm avoids SQL `NULL NOT IN (..)` = NULL, which
    would WRONGLY drop un-glosa'd events.
    """
    approved = select(Glosa.id).where(Glosa.status == GlosaStatus.approved).scalar_subquery()
    return sa.or_(
        ConsumptionEvent.glosa_id.is_(None),
        ConsumptionEvent.glosa_id.not_in(approved),
    )


def _initial_for(contract: Contract) -> float | None:
    if contract.type == ContractType.hour_bank:
        return float(contract.initial_hours) if contract.initial_hours is not None else None
    if contract.type in (ContractType.credit_brl, ContractType.credit_shared):
        return (
            float(contract.initial_amount_brl) if contract.initial_amount_brl is not None else None
        )
    if contract.type == ContractType.service_count:
        return (
            float(contract.initial_service_count)
            if contract.initial_service_count is not None
            else None
        )
    return None  # closed_value / saas_product: no running balance


def consumed_percent_from(contract: Contract, balance: Balance) -> float | None:
    """clamp01((initial - remaining)/initial)*100; None for n/a or 0/absent base."""
    if balance.remaining is None:
        return None
    initial = _initial_for(contract)
    if initial is None or initial == 0:
        return None
    pct = (initial - float(balance.remaining)) / initial * 100.0
    return max(0.0, min(100.0, pct))


@dataclass(slots=True)
class SeriesPoint:
    bucket: dt.date
    value: float


@dataclass(slots=True)
class Series:
    granularity: str  # "day" | "week"
    kind: str  # "hours" | "brl" | "services" | "n/a"
    points: list[SeriesPoint]


@dataclass(slots=True)
class LowBalanceAlert:
    contract_id: uuid.UUID
    code: str
    type: str
    kind: str
    remaining: float
    consumed_percent: float | None
    severity: str  # "warning" | "critical"


class ContractReadService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._cons = ConsumptionService(session)

    async def consumed_percent(self, contract: Contract) -> float | None:
        bal = await self._cons.balance(contract.id)
        return consumed_percent_from(contract, bal)

    async def series(
        self, contract: Contract, *, granularity: str = "day", today: dt.date | None = None
    ) -> Series:
        """Dense (zero-filled) consumption series within the contract window.

        Window = starts_on .. min(ends_on, today). >400 daily buckets forces week
        (H5). Metric per kind; glosa-approved events excluded (S3, centralized).
        """
        today = today or dt.datetime.now(dt.UTC).date()
        end = min(contract.ends_on, today)
        start = contract.starts_on
        if end < start:
            end = start
        span_days = (end - start).days + 1
        if granularity == "day" and span_days > 400:
            granularity = "week"

        bal_kind = (await self._cons.balance(contract.id)).kind

        value_expr: ColumnElement[Any]
        if bal_kind == "hours":
            value_expr = func.coalesce(func.sum(ConsumptionEvent.billable_minutes), 0) / 60.0
            extra: list[ColumnElement[bool]] = []
        elif bal_kind == "brl":
            value_expr = func.coalesce(func.sum(ConsumptionEvent.billable_amount_brl), 0)
            extra = []
        elif bal_kind == "services":
            value_expr = func.count()
            extra = [ConsumptionEvent.source_kind == "service_item"]
        else:  # n/a -> empty/zeros
            return Series(granularity=granularity, kind=bal_kind, points=[])

        # bucket key: date(occurred_at) for day; ISO Monday (date_trunc week) for week.
        bucket_col: ColumnElement[Any]
        if granularity == "week":
            bucket_col = func.date_trunc("week", ConsumptionEvent.occurred_at)
        else:
            bucket_col = func.cast(ConsumptionEvent.occurred_at, sa.Date)
        rows = (
            await self.session.execute(
                select(bucket_col.label("b"), value_expr.label("v"))
                .where(
                    ConsumptionEvent.contract_id == contract.id,
                    not_written_off_predicate(),
                    *extra,
                )
                .group_by(bucket_col)
            )
        ).all()
        by_bucket: dict[dt.date, float] = {}
        for b, v in rows:
            key = b.date() if isinstance(b, dt.datetime) else b
            by_bucket[key] = float(v or 0.0)

        points: list[SeriesPoint] = []
        if granularity == "week":
            cur = start - dt.timedelta(days=start.weekday())  # ISO Monday
            while cur <= end:
                points.append(SeriesPoint(bucket=cur, value=by_bucket.get(cur, 0.0)))
                cur = cur + dt.timedelta(days=7)
        else:
            cur = start
            while cur <= end:
                points.append(SeriesPoint(bucket=cur, value=by_bucket.get(cur, 0.0)))
                cur = cur + dt.timedelta(days=1)
        return Series(granularity=granularity, kind=bal_kind, points=points)

    async def low_balance(self, contract: Contract) -> LowBalanceAlert | None:
        """warning when 0 < remaining/initial < 0.20; critical when <= 0.

        Only saldo-bearing types (hour_bank/credit_brl/credit_shared/service_count);
        closed_value/saas_product (kind=='n/a') NEVER alert.
        """
        bal = await self._cons.balance(contract.id)
        if bal.kind == "n/a" or bal.remaining is None:
            return None
        initial = _initial_for(contract)
        if initial is None or initial == 0:
            return None
        remaining_pct = float(bal.remaining) / initial
        if remaining_pct >= 0.20:
            return None
        severity = "critical" if remaining_pct <= 0 else "warning"
        return LowBalanceAlert(
            contract_id=contract.id,
            code=contract.code,
            type=contract.type.value,
            kind=bal.kind,
            remaining=float(bal.remaining),
            consumed_percent=consumed_percent_from(contract, bal),
            severity=severity,
        )
