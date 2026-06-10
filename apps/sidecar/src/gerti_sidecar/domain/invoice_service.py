"""InvoiceService — constrói a fatura interna a partir de um ciclo (#1B) + transições.

create_from_cycle: lê o ciclo (tenant-scoped) + seus consumption_event no período,
agrega em linhas por source_kind, numera sequencialmente por tenant sob lock, e
grava 1 fatura `open` (idempotente por ciclo via UNIQUE → InvoiceAlreadyExists).
Transições: mark_paid/mark_void (terminais), mark_overdue_due (batch p/ worker).

Valores monetários da fatura ficam em centavos (int). billable_amount_brl (Numeric
BRL) é convertido com arredondamento HALF_UP.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import (
    CycleNotClosable,
    InvoiceAlreadyExists,
    InvoiceError,
)
from gerti_sidecar.models import (
    ConsumptionEvent,
    Contract,
    ContractCycle,
    Invoice,
    InvoiceLine,
)
from gerti_sidecar.models.enums import CycleStatus, InvoiceStatus

# Default config — número de dias até o vencimento da fatura emitida.
DEFAULT_DUE_DAYS = 15

# Rótulos amigáveis por source_kind (cai no próprio kind se ausente).
_KIND_LABELS = {
    "ticket_work": "Atendimento (horas)",
    "travel": "Deslocamento",
}

# Unidade exibida por source_kind.
_KIND_UNIT = {
    "ticket_work": "h",
    "travel": "serviço",
}


def _brl_to_cents(value: Decimal | float) -> int:
    """Converte um valor BRL para centavos com arredondamento bancário HALF_UP."""
    dec = Decimal(str(value)) if not isinstance(value, Decimal) else value
    return int((dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class InvoiceService:
    def __init__(self, session: AsyncSession, *, due_days: int = DEFAULT_DUE_DAYS) -> None:
        self.session = session
        self.due_days = due_days

    async def create_from_cycle(
        self, cycle_id: uuid.UUID, *, issued_at: dt.datetime | None = None
    ) -> Invoice:
        cycle = await self.session.get(ContractCycle, cycle_id)
        if cycle is None:
            raise InvoiceError("ciclo inexistente neste tenant")
        if cycle.status == CycleStatus.open:
            raise CycleNotClosable("ciclo ainda aberto — feche-o antes de faturar")
        contract = await self.session.get(Contract, cycle.contract_id)
        if contract is None:
            raise InvoiceError("contrato do ciclo inexistente")

        start = dt.datetime.combine(cycle.period_start, dt.time.min, tzinfo=dt.UTC)
        end = dt.datetime.combine(cycle.period_end, dt.time.max, tzinfo=dt.UTC)
        events = (
            (
                await self.session.execute(
                    select(ConsumptionEvent)
                    .where(
                        ConsumptionEvent.contract_id == contract.id,
                        ConsumptionEvent.occurred_at >= start,
                        ConsumptionEvent.occurred_at <= end,
                    )
                    .order_by(ConsumptionEvent.occurred_at.asc(), ConsumptionEvent.id.asc())
                )
            )
            .scalars()
            .all()
        )

        # Agrega por source_kind, preservando a ordem de aparição.
        agg: OrderedDict[str, dict[str, Decimal]] = OrderedDict()
        for ev in events:
            bucket = agg.setdefault(ev.source_kind, {"minutes": Decimal(0), "amount": Decimal(0)})
            bucket["minutes"] += Decimal(str(ev.billable_minutes))
            bucket["amount"] += Decimal(str(ev.billable_amount_brl))

        now = issued_at or dt.datetime.now(dt.UTC)
        number = await self._next_number(contract.tenant_id)
        invoice = Invoice(
            tenant_id=contract.tenant_id,
            contract_id=contract.id,
            cycle_id=cycle.id,
            number=number,
            status=InvoiceStatus.open,
            issued_at=now,
            due_at=now + dt.timedelta(days=self.due_days),
            period_start=cycle.period_start,
            period_end=cycle.period_end,
            currency="BRL",
            subtotal_cents=0,
            total_cents=0,
        )
        # Savepoint ABERTO antes do add: a colisão de UNIQUE(cycle_id) é desfeita
        # sem derrubar a transação externa (que carrega o GUC app.current_tenant).
        # begin_nested() faz autoflush; por isso o add vem DENTRO do savepoint.
        sp = await self.session.begin_nested()
        try:
            self.session.add(invoice)
            await self.session.flush()
        except IntegrityError as exc:
            await sp.rollback()
            raise InvoiceAlreadyExists("ciclo já possui fatura") from exc

        subtotal = 0
        for position, (kind, bucket) in enumerate(agg.items()):
            amount_cents = _brl_to_cents(bucket["amount"])
            minutes = bucket["minutes"]
            unit = _KIND_UNIT.get(kind, "R$")
            # quantity em horas p/ ticket_work; senão nº de eventos como proxy.
            if unit == "h":
                quantity = (minutes / Decimal(60)).quantize(Decimal("0.01"))
            else:
                quantity = Decimal(1)
            unit_price_cents = int(Decimal(amount_cents) / quantity) if quantity else amount_cents
            subtotal += amount_cents
            self.session.add(
                InvoiceLine(
                    invoice_id=invoice.id,
                    tenant_id=contract.tenant_id,
                    description=_KIND_LABELS.get(kind, kind),
                    quantity=quantity,
                    unit=unit,
                    unit_price_cents=unit_price_cents,
                    amount_cents=amount_cents,
                    position=position,
                )
            )

        invoice.subtotal_cents = subtotal
        invoice.total_cents = subtotal  # sem impostos nesta fase
        await self.session.flush()
        return invoice

    async def _next_number(self, tenant_id: uuid.UUID) -> int:
        """Próximo número sequencial por tenant, sob advisory lock transacional.

        O advisory lock por tenant serializa create_from_cycle concorrentes (UI +
        worker) evitando corrida no coalesce(max)+1. O lock cai no fim da
        transação (pg_advisory_xact_lock).
        """
        # hashtext do uuid → bigint estável p/ a chave do advisory lock por tenant.
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:t))"),
            {"t": str(tenant_id)},
        )
        current = await self.session.scalar(
            select(func.coalesce(func.max(Invoice.number), 0)).where(Invoice.tenant_id == tenant_id)
        )
        return int(current or 0) + 1

    async def lines_for(self, invoice_id: uuid.UUID) -> list[InvoiceLine]:
        return list(
            (
                await self.session.execute(
                    select(InvoiceLine)
                    .where(InvoiceLine.invoice_id == invoice_id)
                    .order_by(InvoiceLine.position.asc())
                )
            )
            .scalars()
            .all()
        )

    async def _get(self, invoice_id: uuid.UUID) -> Invoice:
        inv = await self.session.get(Invoice, invoice_id)
        if inv is None:
            raise InvoiceError("fatura inexistente neste tenant")
        return inv

    async def mark_paid(self, invoice_id: uuid.UUID) -> Invoice:
        inv = await self._get(invoice_id)
        if inv.status in (InvoiceStatus.paid, InvoiceStatus.void):
            raise InvoiceError(f"transição inválida: {inv.status} → paid (terminal)")
        inv.status = InvoiceStatus.paid
        await self.session.flush()
        return inv

    async def mark_void(self, invoice_id: uuid.UUID) -> Invoice:
        inv = await self._get(invoice_id)
        if inv.status in (InvoiceStatus.paid, InvoiceStatus.void):
            raise InvoiceError(f"transição inválida: {inv.status} → void (terminal)")
        inv.status = InvoiceStatus.void
        await self.session.flush()
        return inv

    async def mark_overdue_due(self, *, today: dt.date | None = None) -> int:
        """Marca como `overdue` toda fatura `open` cujo due_at já passou. Retorna a contagem."""
        day = today or dt.datetime.now(dt.UTC).date()
        cutoff = dt.datetime.combine(day, dt.time.min, tzinfo=dt.UTC)
        result = await self.session.execute(
            update(Invoice)
            .where(Invoice.status == InvoiceStatus.open, Invoice.due_at < cutoff)
            .values(status=InvoiceStatus.overdue)
        )
        await self.session.flush()
        return int(result.rowcount or 0)
