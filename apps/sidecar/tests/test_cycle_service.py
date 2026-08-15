"""CycleService.close: consumo, franquia efetiva, excedente, acúmulo entre ciclos."""

import datetime as dt
import uuid

import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.domain.invoice_service import InvoiceService
from gerti_sidecar.models import Contract, ContractCycle
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus


async def _hour_bank_contract(s, *, code: str, accumulate: bool) -> Contract:
    """Banco de horas de 40 h/mês a R$ 180/h — o cenário do defeito de acúmulo."""
    return await ContractService(s).create(
        NewContract(
            code=code,
            type=ContractType.hour_bank,
            starts_on=dt.date(2026, 1, 1),
            ends_on=dt.date(2026, 12, 31),
            initial_hours=40,
            unit_price_brl=180,
            billing_period_months=1,
            closing_period_months=1,
            accumulate_balance_between_cycles=accumulate,
            created_by="w",
        )
    )


async def _closed_month(s, contract, *, month: int, hours: float, last_day: int = 28):
    """Abre um ciclo de fechamento do mês, lança `hours` de trabalho e fecha."""
    cyc = ContractCycle(
        contract_id=contract.id,
        kind=CycleKind.closing,
        period_start=dt.date(2026, month, 1),
        period_end=dt.date(2026, month, last_day),
    )
    s.add(cyc)
    await s.flush()
    await ConsumptionService(s).record(
        RecordConsumption(
            contract_id=contract.id,
            occurred_at=dt.datetime(2026, month, 10, tzinfo=dt.UTC),
            source_kind="ticket_work",
            source_ref=f"{contract.code}:{month}",
            billable_minutes=hours * 60,
            recorded_by="t",
            webhook_event_id=uuid.uuid4(),
        )
    )
    totals = await CycleService(s).close(cyc.id)
    return cyc, totals


@pytest.mark.asyncio
async def test_close_cycle_overage_and_accrual(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        c = await ContractService(s).create(
            NewContract(
                code="HB",
                type=ContractType.hour_bank,
                starts_on=dt.date(2026, 1, 1),
                ends_on=dt.date(2026, 12, 31),
                initial_hours=2,
                unit_price_brl=150,
                billing_period_months=1,
                closing_period_months=1,
                accumulate_balance_between_cycles=False,
                created_by="w",
            )
        )
        cyc = ContractCycle(
            contract_id=c.id,
            kind=CycleKind.closing,
            period_start=dt.date(2026, 1, 1),
            period_end=dt.date(2026, 1, 31),
        )
        s.add(cyc)
        await s.flush()
        cons = ConsumptionService(s)
        await cons.record(
            RecordConsumption(
                contract_id=c.id,
                occurred_at=dt.datetime(2026, 1, 10, tzinfo=dt.UTC),
                source_kind="ticket_work",
                source_ref="a:1",
                billable_minutes=180,
                recorded_by="t",
                webhook_event_id=uuid.uuid4(),
            )
        )
        totals = await CycleService(s).close(cyc.id)
        # consumed 3h, franchise/initial 2h → 1h overage * 150 = 150
        assert totals["consumed_minutes"] == 180
        assert totals["overage_minutes"] == 60
        assert float(totals["overage_amount_brl"]) == 150.0
        assert totals["carry_over"] == 0  # accrual disabled
        refreshed = await s.get(ContractCycle, cyc.id)
        assert refreshed.status == CycleStatus.closed and refreshed.closed_at is not None
        # consumption events stamped with this closing cycle
        from sqlalchemy import func, select

        from gerti_sidecar.models import ConsumptionEvent

        n = await s.scalar(select(func.count()).where(ConsumptionEvent.closing_cycle_id == cyc.id))
        assert n == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("accumulate", "expected_franchise", "expected_overage_min", "expected_total_cents"),
    [
        # Jan sobrou 10 h; com acúmulo a franquia de fev é 50 h → 45 h cabem → R$ 0,00.
        (True, 3000.0, 0.0, 0),
        # Sem acúmulo a franquia volta a 40 h → 5 h de excedente a R$ 180 = R$ 900,00.
        (False, 2400.0, 300.0, 90000),
    ],
    ids=["acumula", "nao_acumula"],
)
async def test_carry_over_feeds_next_cycle_franchise(
    session,
    app_session_factory,
    seed_two_tenants,
    accumulate,
    expected_franchise,
    expected_overage_min,
    expected_total_cents,
):
    """ "Acumular saldo entre ciclos" muda a franquia do ciclo seguinte — e a fatura.

    40 h/mês a R$ 180/h. Jan consome 30 h (sobram 10 h). Fev consome 45 h. Antes
    da correção o `carry_over` era gravado e nunca lido: a franquia de fev voltava
    a 40 h e o cliente recebia R$ 900,00 de excedente que não existia.
    """
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        contract = await _hour_bank_contract(s, code=f"HB-ACC-{accumulate}", accumulate=accumulate)

        _jan, jan_totals = await _closed_month(s, contract, month=1, hours=30, last_day=31)
        assert jan_totals["consumed_minutes"] == 1800
        assert jan_totals["overage_minutes"] == 0
        # carry_over só existe com o acúmulo ligado
        assert jan_totals["carry_over"] == (600.0 if accumulate else 0.0)

        feb, feb_totals = await _closed_month(s, contract, month=2, hours=45)
        assert feb_totals["base_franchise_minutes"] == 2400.0
        assert feb_totals["carry_in_minutes"] == (600.0 if accumulate else 0.0)
        assert feb_totals["franchise_minutes"] == expected_franchise
        assert feb_totals["overage_minutes"] == expected_overage_min
        assert float(feb_totals["overage_amount_brl"]) == expected_overage_min / 60.0 * 180.0

        inv = await InvoiceService(s).create_from_cycle(feb.id)
        assert inv.total_cents == expected_total_cents


@pytest.mark.asyncio
async def test_carry_over_accumulates_in_chain(session, app_session_factory, seed_two_tenants):
    """O saldo passa adiante por vários ciclos: o carry de N já embute o de N-1."""
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        contract = await _hour_bank_contract(s, code="HB-CHAIN", accumulate=True)

        # Jan: 40 h de franquia, 10 h usadas → sobram 30 h.
        _jan, jan = await _closed_month(s, contract, month=1, hours=10, last_day=31)
        assert jan["franchise_minutes"] == 2400.0
        assert jan["carry_over"] == 1800.0

        # Fev: 40 h + 30 h = 70 h, 20 h usadas → sobram 50 h.
        _feb, feb = await _closed_month(s, contract, month=2, hours=20)
        assert feb["carry_in_minutes"] == 1800.0
        assert feb["franchise_minutes"] == 4200.0
        assert feb["overage_minutes"] == 0
        assert feb["carry_over"] == 3000.0

        # Mar: 40 h + 50 h = 90 h, 100 h usadas → 10 h de excedente, carry zera.
        mar_cycle, mar = await _closed_month(s, contract, month=3, hours=100, last_day=31)
        assert mar["carry_in_minutes"] == 3000.0
        assert mar["franchise_minutes"] == 5400.0
        assert mar["overage_minutes"] == 600.0
        assert float(mar["overage_amount_brl"]) == 1800.0
        assert mar["carry_over"] == 0.0

        inv = await InvoiceService(s).create_from_cycle(mar_cycle.id)
        assert inv.total_cents == 180000
        lines = await InvoiceService(s).lines_for(inv.id)
        # 90 h dentro da franquia + 10 h excedentes = 100 h consumidas, sem dobra.
        assert [(line.description, float(line.quantity)) for line in lines] == [
            ("Horas dentro da franquia", 90.0),
            ("Horas excedentes", 10.0),
        ]
