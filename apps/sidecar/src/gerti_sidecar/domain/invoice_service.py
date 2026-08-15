"""InvoiceService — constrói a fatura interna a partir de um ciclo (#1B) + transições.

create_from_cycle: lê o ciclo (tenant-scoped) + seus consumption_event no período,
agrega em linhas por source_kind, numera sequencialmente por tenant sob lock, e
grava 1 fatura `open` (idempotente por ciclo via UNIQUE → InvoiceAlreadyExists).
Transições: mark_paid/mark_void (terminais), mark_overdue_due (batch p/ worker).

Além do consumo, a fatura reflete o que foi **contratado** (T-R15.4):

- `closed_value` / `saas_product` → linha de **mensalidade** com o valor fixo
  contratado (`contract.initial_amount_brl`), que é o campo que a UI rotula
  "Valor inicial (R$)" e que `contract_service._REQUIRED` exige nesses tipos;
- `hour_bank` → as horas do ciclo aparecem **partidas em duas linhas que somam o
  consumido**: `Horas dentro da franquia` (quantidade = `min(consumido, franquia
  efetiva)`, R$ 0,00) e `Horas excedentes` (o que passou da franquia, precificado).
  Emitir a linha de consumo com o total consumido **e** a de excedente somaria as
  horas duas vezes na cara do cliente (12 h consumidas viravam 12 h + 2 h = 14 h).
  Ambos os números saem de `cycle.totals` (`CycleService.close`) — fonte única.
  Dentro da franquia não há linha de excedente (fatura zerada aí é legítima).

Antes disso, só o consumo era somado — e o worker (`reconciliation_service`) só
precifica tipos de crédito, então `hour_bank`/`closed_value`/`saas_product`
faturavam R$ 0,00 sem erro nem alarme.

**`service_count` continua faturando R$ 0,00 — de propósito, por ora.** Contrato
por limite de atendimento não gera nenhuma linha aqui: não há mensalidade fixa
(o tipo não exige `initial_amount_brl`) nem excedente calculado no fechamento, e
o consumo desses contratos não é precificado pelo worker. Fazer `service_count`
consumir e cobrar de verdade é a tarefa **T-R3.3 (Onda 5)**; até lá, a fatura
desse tipo sai zerada e isso é conhecido, não um defeito silencioso.

Valores monetários da fatura ficam em centavos (int). billable_amount_brl (Numeric
BRL) é convertido com arredondamento HALF_UP.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import uuid
from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import (
    CycleNotClosable,
    InvoiceAlreadyExists,
    InvoiceError,
)
from gerti_sidecar.domain.notification_service import NotificationService
from gerti_sidecar.models import (
    ConsumptionEvent,
    Contract,
    ContractCycle,
    Invoice,
    InvoiceLine,
    PortalUserRole,
)
from gerti_sidecar.models.enums import ContractType, CycleStatus, InvoiceStatus, PortalRole

logger = logging.getLogger(__name__)

# Default config — número de dias até o vencimento da fatura emitida.
DEFAULT_DUE_DAYS = 15

# Kinds sintéticos (não vêm de consumption_event; derivam do contrato/ciclo).
KIND_MONTHLY_FEE = "monthly_fee"
KIND_HOUR_BANK_OVERAGE = "hour_bank_overage"
KIND_HOUR_BANK_INCLUDED = "hour_bank_included"

# Tipos de contrato que faturam um valor fixo contratado por ciclo.
_FIXED_FEE_TYPES = (ContractType.closed_value, ContractType.saas_product)

# Rótulos amigáveis por source_kind (cai no próprio kind se ausente).
_KIND_LABELS = {
    "ticket_work": "Atendimento (horas)",
    "travel": "Deslocamento",
    KIND_MONTHLY_FEE: "Mensalidade",
    KIND_HOUR_BANK_INCLUDED: "Horas dentro da franquia",
    KIND_HOUR_BANK_OVERAGE: "Horas excedentes",
}

# Unidade exibida por source_kind.
_KIND_UNIT = {
    "ticket_work": "h",
    "travel": "serviço",
    KIND_MONTHLY_FEE: "mês",
    KIND_HOUR_BANK_INCLUDED: "h",
    KIND_HOUR_BANK_OVERAGE: "h",
}


def _brl_to_cents(value: Decimal | float) -> int:
    """Converte um valor BRL para centavos com arredondamento bancário HALF_UP."""
    dec = Decimal(str(value)) if not isinstance(value, Decimal) else value
    return int((dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclasses.dataclass(slots=True)
class _LineSpec:
    """Uma linha da fatura antes de virar InvoiceLine (valores ainda em BRL)."""

    kind: str
    quantity: Decimal
    amount_brl: Decimal


def _hours(minutes: Decimal) -> Decimal:
    return (minutes / Decimal(60)).quantize(Decimal("0.01"))


def _fixed_fee_lines(contract: Contract) -> list[_LineSpec]:
    """Mensalidade contratada de closed_value/saas_product (1 por ciclo faturado).

    O valor vem de `contract.initial_amount_brl` — o único campo do modelo que
    carrega o valor fixo contratado nesses dois tipos (exigido por
    `contract_service._REQUIRED`, rotulado "Valor inicial (R$)" na UI).
    """
    if contract.type not in _FIXED_FEE_TYPES:
        return []
    amount = Decimal(str(contract.initial_amount_brl or 0))
    if amount <= 0:
        return []
    return [_LineSpec(kind=KIND_MONTHLY_FEE, quantity=Decimal(1), amount_brl=amount)]


def _franchise_minutes(contract: Contract, cycle: ContractCycle) -> Decimal | None:
    """Franquia EFETIVA do ciclo (base + acúmulo), do snapshot do fechamento.

    `None` quando não se aplica (contrato não é `hour_bank`) ou quando o ciclo não
    tem `totals` — sem snapshot também não há linha de excedente, então a linha de
    consumo não pode ser recortada (recortar esconderia horas da fatura).
    """
    if contract.type != ContractType.hour_bank:
        return None
    totals = cycle.totals or {}
    raw = totals.get("franchise_minutes")
    if not isinstance(raw, int | float):
        return None
    return max(Decimal(0), Decimal(str(raw)))


def _consumption_lines(
    contract: Contract, cycle: ContractCycle, agg: OrderedDict[str, dict[str, Decimal]]
) -> list[_LineSpec]:
    """Linhas de consumo agregadas por source_kind.

    Em `hour_bank`, as linhas medidas em horas viram `Horas dentro da franquia`
    com a quantidade **recortada na franquia efetiva** — o que passa dela é a
    linha de excedente (`_overage_lines`). Assim consumo + excedente somam
    exatamente o consumido; sem o recorte, o cliente lia as horas duas vezes.
    """
    franchise_left = _franchise_minutes(contract, cycle)
    specs: list[_LineSpec] = []
    for kind, bucket in agg.items():
        unit = _KIND_UNIT.get(kind, "R$")
        if unit == "h" and franchise_left is not None:
            included = min(bucket["minutes"], franchise_left)
            franchise_left -= included
            if included <= 0:
                continue
            specs.append(
                _LineSpec(
                    kind=KIND_HOUR_BANK_INCLUDED,
                    quantity=_hours(included),
                    amount_brl=bucket["amount"],
                )
            )
            continue
        # quantity em horas p/ kinds medidos em tempo; senão 1 (nº de eventos como proxy).
        quantity = _hours(bucket["minutes"]) if unit == "h" else Decimal(1)
        specs.append(_LineSpec(kind=kind, quantity=quantity, amount_brl=bucket["amount"]))
    return specs


def _overage_lines(contract: Contract, cycle: ContractCycle) -> list[_LineSpec]:
    """Excedente de banco de horas, tal como calculado no fechamento do ciclo.

    Fonte única da verdade: `cycle.totals` (CycleService.close). Não recalculamos
    aqui — recalcular divergiria do snapshot do fechamento. Ciclo sem totals
    (fechado por versão antiga, ou ciclo de faturamento) → sem linha.
    """
    if contract.type != ContractType.hour_bank:
        return []
    totals = cycle.totals or {}
    amount = Decimal(str(totals.get("overage_amount_brl") or 0))
    minutes = Decimal(str(totals.get("overage_minutes") or 0))
    if amount <= 0:
        return []
    return [_LineSpec(kind=KIND_HOUR_BANK_OVERAGE, quantity=_hours(minutes), amount_brl=amount)]


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

        # Ordem da fatura: mensalidade contratada → consumo → excedente do ciclo.
        specs: list[_LineSpec] = _fixed_fee_lines(contract)
        specs.extend(_consumption_lines(contract, cycle, agg))
        specs.extend(_overage_lines(contract, cycle))

        subtotal = 0
        for position, spec in enumerate(specs):
            amount_cents = _brl_to_cents(spec.amount_brl)
            unit_price_cents = (
                int(Decimal(amount_cents) / spec.quantity) if spec.quantity else amount_cents
            )
            subtotal += amount_cents
            self.session.add(
                InvoiceLine(
                    invoice_id=invoice.id,
                    tenant_id=contract.tenant_id,
                    description=_KIND_LABELS.get(spec.kind, spec.kind),
                    quantity=spec.quantity,
                    unit=_KIND_UNIT.get(spec.kind, "R$"),
                    unit_price_cents=unit_price_cents,
                    amount_cents=amount_cents,
                    position=position,
                )
            )

        invoice.subtotal_cents = subtotal
        invoice.total_cents = subtotal  # sem impostos nesta fase
        await self.session.flush()

        # Notificação (Spec #3 V3): best-effort — jamais derruba a fatura já
        # gravada. Falha na emissão só vira log.
        try:
            await self._notify_admins_invoice_issued(invoice)
        except Exception:
            logger.exception(
                "falha ao emitir notificação invoice_issued (invoice_id=%s)", invoice.id
            )

        return invoice

    async def _notify_admins_invoice_issued(self, invoice: Invoice) -> None:
        admin_logins = (
            (
                await self.session.execute(
                    select(PortalUserRole.customer_login).where(
                        PortalUserRole.role == PortalRole.admin
                    )
                )
            )
            .scalars()
            .all()
        )
        notifier = NotificationService(self.session)
        for login in admin_logins:
            await notifier.emit(
                recipient_login=login,
                kind="invoice_issued",
                title=f"Fatura #{invoice.number:04d} emitida",
                body=f"Vencimento em {invoice.due_at.date().isoformat()}.",
                link_path=f"/faturas/{invoice.number}",
                at=invoice.issued_at,
            )

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
        # rowcount existe no CursorResult de um UPDATE; cast p/ o mypy strict.
        return int(cast("CursorResult[Any]", result).rowcount or 0)
