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
from gerti_sidecar.models import ConsumptionEvent, Contract, ContractCycle, Glosa
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

    async def _window_buckets(
        self, contract: Contract, *, window: str, count: int, today: dt.date
    ) -> list[tuple[dt.date, dt.date, dt.date]]:
        """Baldes (rótulo, início, fim) da janela pedida — R18a, T-R18a.1/T-R18a.4.

        *"vejo nos últimos três meses qual foi o ciclo de utilização dele"* (11:00).

        Dois modos, porque **não sabemos qual ele quis** (suposição S3):

        • `months` — N meses-calendário terminando no mês de `today`. Previsível
          e é o que "últimos três meses" diz ao pé da letra.
        • `cycles` — os N últimos ciclos de faturamento do contrato, que é o que
          "ciclo de utilização" diz. Só coincide com meses quando o contrato é
          mensal.

        No modo `cycles`, contrato sem nenhum ciclo registrado **cai para
        `months`** em vez de devolver série vazia: um gráfico em branco seria
        lido como "não consumiu nada", que é diferente de "ainda não fechamos
        ciclo nenhum".
        """
        if window == "cycles":
            rows = (
                (
                    await self.session.execute(
                        select(ContractCycle)
                        .where(ContractCycle.contract_id == contract.id)
                        .order_by(ContractCycle.period_start.desc())
                        .limit(count)
                    )
                )
                .scalars()
                .all()
            )
            if rows:
                return [(c.period_start, c.period_start, c.period_end) for c in reversed(rows)]

        # months (pedido, ou fallback de `cycles` sem ciclo nenhum)
        buckets: list[tuple[dt.date, dt.date, dt.date]] = []
        first_of_this_month = today.replace(day=1)
        month_starts: list[dt.date] = []
        cur = first_of_this_month
        for _ in range(count):
            month_starts.append(cur)
            cur = (cur - dt.timedelta(days=1)).replace(day=1)
        for start in reversed(month_starts):
            nxt = (start + dt.timedelta(days=32)).replace(day=1)
            buckets.append((start, start, nxt - dt.timedelta(days=1)))
        return buckets

    async def series(
        self,
        contract: Contract,
        *,
        granularity: str = "day",
        today: dt.date | None = None,
        window: str | None = None,
        count: int | None = None,
    ) -> Series:
        """Dense (zero-filled) consumption series.

        Sem `window`: comportamento histórico — a vida inteira do contrato
        (`starts_on` .. `min(ends_on, today)`), dia a dia, degradando para
        semana acima de 400 baldes (H5). É o que o portal usa, e não muda.

        Com `window` (`"months"` ou `"cycles"`): a janela do R18a — N baldes,
        um por mês ou por ciclo. A unidade (`kind`) é a mesma nos dois casos:
        contrato de hora devolve horas, contrato de crédito devolve reais.

        A regra S3 de glosa aprovada continua centralizada e aplicada.
        """
        today = today or dt.datetime.now(dt.UTC).date()

        if window is not None:
            return await self._windowed_series(
                contract, window=window, count=count or 3, today=today
            )

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

    async def _windowed_series(
        self, contract: Contract, *, window: str, count: int, today: dt.date
    ) -> Series:
        """Série da janela do R18a: um ponto por mês ou por ciclo.

        Cada balde é somado no seu próprio intervalo, e não há degradação de
        granularidade: 3 baldes são 3 baldes. Consumo fora da janela **não**
        entra — é o aceite A18a.3, e é o que diferencia esta série da antiga.
        """
        count = max(1, min(count, 24))  # teto: 24 baldes é 2 anos, já é relatório
        buckets = await self._window_buckets(contract, window=window, count=count, today=today)
        bal_kind = (await self._cons.balance(contract.id)).kind

        value_expr: ColumnElement[Any]
        extra: list[ColumnElement[bool]] = []
        if bal_kind == "hours":
            value_expr = func.coalesce(func.sum(ConsumptionEvent.billable_minutes), 0) / 60.0
        elif bal_kind == "brl":
            value_expr = func.coalesce(func.sum(ConsumptionEvent.billable_amount_brl), 0)
        elif bal_kind == "services":
            value_expr = func.count()
            extra = [ConsumptionEvent.source_kind == "service_item"]
        else:  # closed_value / saas_product: sem saldo, sem série (A18a.4)
            return Series(granularity=window, kind=bal_kind, points=[])

        points: list[SeriesPoint] = []
        for label, start, end in buckets:
            # `occurred_at` é timestamptz; comparar com o DIA seguinte ao fim do
            # balde evita perder o que aconteceu depois das 00:00 do último dia.
            value = await self.session.scalar(
                select(value_expr).where(
                    ConsumptionEvent.contract_id == contract.id,
                    ConsumptionEvent.occurred_at >= dt.datetime.combine(start, dt.time.min, dt.UTC),
                    ConsumptionEvent.occurred_at
                    < dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min, dt.UTC),
                    not_written_off_predicate(),
                    *extra,
                )
            )
            points.append(SeriesPoint(bucket=label, value=float(value or 0.0)))
        return Series(granularity=window, kind=bal_kind, points=points)

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
