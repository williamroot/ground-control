"""T-R15.5 — boleto e nota fiscal da fatura, pelo Asaas.

I-4 fechou o emissor: o Asaas emite os dois, e o que faltava era acionar a
cobrança a partir de `gerti.invoice`.

O teste que mais importa é `test_charging_twice_does_not_create_a_second_slip`
— boleto duplicado é o cliente pagando duas vezes.
"""

from __future__ import annotations

import datetime as dt

import pytest

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.invoice_charge_service import (
    ChargingDisabled,
    ChargingRefused,
    InvoiceChargeService,
)
from gerti_sidecar.models import (
    Contract,
    ContractBillingParty,
    Invoice,
    Tenant,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType, InvoiceStatus

D = dt.date


class _FakeAsaas:
    """Registra o que foi pedido — a asserção é sobre a CHAMADA, não sobre mock."""

    def __init__(self) -> None:
        self.customers: list[dict] = []
        self.payments: list[dict] = []
        self.invoices: list[dict] = []
        self.payment_status = "PENDING"

    async def find_or_create_customer(self, **kw):
        self.customers.append(kw)
        return {"id": "cus_1"}

    async def create_payment(self, **kw):
        self.payments.append(kw)
        return {
            "id": f"pay_{len(self.payments)}",
            "status": "PENDING",
            "bankSlipUrl": "https://asaas.test/boleto.pdf",
            "invoiceUrl": "https://asaas.test/fatura",
        }

    async def schedule_invoice(self, **kw):
        self.invoices.append(kw)
        return {"id": "nfe_1", "status": "SCHEDULED", "pdfUrl": None}

    async def get_payment(self, payment_id):
        return {
            "id": payment_id,
            "status": self.payment_status,
            "bankSlipUrl": "https://asaas.test/boleto.pdf",
        }

    async def get_invoice(self, invoice_id):
        return {"id": invoice_id, "status": "AUTHORIZED", "pdfUrl": "https://asaas.test/nfe.pdf"}


async def _seed(session, *, document="12345678000199", total_cents=45000, billing_party=False):
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
    t = Tenant(
        legal_name="Acme Ltda",
        trade_name="Acme",
        document=document,
        znuny_customer_id="ACME",
        znuny_instance_id=inst.id,
        subdomain="acme",
        contact_email="financeiro@acme.test",
    )
    session.add(t)
    await session.flush()
    c = Contract(
        tenant_id=t.id,
        code="ACM-2026",
        type=ContractType.closed_value,
        starts_on=D(2026, 1, 1),
        ends_on=D(2026, 12, 31),
        initial_amount_brl=450,
        created_by="seed",
    )
    session.add(c)
    await session.flush()
    if billing_party:
        session.add(
            ContractBillingParty(
                contract_id=c.id,
                legal_name="Holding Acme S.A.",
                document="99887766000155",
                fiscal_address={"city": "BH"},
            )
        )
    now = dt.datetime(2026, 6, 1, 12, tzinfo=dt.UTC)
    inv = Invoice(
        tenant_id=t.id,
        contract_id=c.id,
        number=1,
        status=InvoiceStatus.open,
        issued_at=now,
        due_at=now + dt.timedelta(days=15),
        period_start=D(2026, 5, 1),
        period_end=D(2026, 5, 31),
        subtotal_cents=total_cents,
        total_cents=total_cents,
    )
    session.add(inv)
    await session.flush()
    await session.commit()
    return t, inv


def _svc(session, asaas=None, *, enabled=True):
    return InvoiceChargeService(session, asaas, enabled=enabled)


# ── fail-safe ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_asaas_disabled_refuses_clearly(engine, app_session_factory, session):
    """Sem chave, o operador precisa ler 'está desligado', não um erro torto."""
    t, inv = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(ChargingDisabled):
            await _svc(s, None, enabled=False).issue_bank_slip(inv.id)


# ── boleto ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_issuing_a_bank_slip_stores_the_link(engine, app_session_factory, session):
    t, inv = await _seed(session)
    fake = _FakeAsaas()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        charged = await _svc(s, fake).issue_bank_slip(inv.id)
    assert charged.asaas_payment_id == "pay_1"
    assert charged.asaas_bank_slip_url == "https://asaas.test/boleto.pdf"
    payment = fake.payments[0]
    assert payment["billing_type"] == "BOLETO"
    assert payment["value_cents"] == 45000
    assert payment["due_date"] == "2026-06-16"
    # É por esta referência que o webhook reencontra a fatura.
    assert payment["external_reference"] == f"invoice:{inv.id}"


@pytest.mark.asyncio
async def test_charging_twice_does_not_create_a_second_slip(engine, app_session_factory, session):
    """Boleto duplicado é o cliente pagando duas vezes."""
    t, inv = await _seed(session)
    fake = _FakeAsaas()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = _svc(s, fake)
        first = await svc.issue_bank_slip(inv.id)
        second = await svc.issue_bank_slip(inv.id)
    assert first.asaas_payment_id == second.asaas_payment_id
    assert len(fake.payments) == 1, "emitiu um segundo boleto para a mesma fatura"


@pytest.mark.asyncio
async def test_a_zero_invoice_is_not_charged(engine, app_session_factory, session):
    t, inv = await _seed(session, total_cents=0)
    fake = _FakeAsaas()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(ChargingRefused, match="sem valor"):
            await _svc(s, fake).issue_bank_slip(inv.id)
    assert fake.payments == []


@pytest.mark.asyncio
async def test_a_client_without_a_document_is_refused_before_the_call(
    engine, app_session_factory, session
):
    """Melhor recusar com o motivo do que deixar o Asaas devolver erro cru."""
    t, inv = await _seed(session, document="")
    fake = _FakeAsaas()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(ChargingRefused, match="CNPJ/CPF"):
            await _svc(s, fake).issue_bank_slip(inv.id)
    assert fake.customers == []


@pytest.mark.asyncio
async def test_the_billing_party_is_who_gets_charged(engine, app_session_factory, session):
    """'Faturar para outro CNPJ' só existe se o boleto sair no nome dele."""
    t, inv = await _seed(session, billing_party=True)
    fake = _FakeAsaas()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await _svc(s, fake).issue_bank_slip(inv.id)
    assert fake.customers[0]["name"] == "Holding Acme S.A."
    assert fake.customers[0]["cpf_cnpj"] == "99887766000155"


# ── nota fiscal ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_nfe_requires_the_charge_first(engine, app_session_factory, session):
    """A nota do Asaas pendura numa cobrança; emitir boleto por baixo seria pior."""
    t, inv = await _seed(session)
    fake = _FakeAsaas()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(ChargingRefused, match="emita a cobrança antes"):
            await _svc(s, fake).issue_nfe(inv.id)
    assert fake.payments == []
    assert fake.invoices == []


@pytest.mark.asyncio
async def test_nfe_is_scheduled_over_the_payment(engine, app_session_factory, session):
    t, inv = await _seed(session)
    fake = _FakeAsaas()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = _svc(s, fake)
        await svc.issue_bank_slip(inv.id)
        issued = await svc.issue_nfe(inv.id, municipal_service_code="1.07")
    assert issued.nfe_id == "nfe_1"
    assert issued.nfe_status == "SCHEDULED"
    assert fake.invoices[0]["payment_id"] == "pay_1"
    assert fake.invoices[0]["municipal_service_code"] == "1.07"


@pytest.mark.asyncio
async def test_nfe_is_issued_only_once(engine, app_session_factory, session):
    t, inv = await _seed(session)
    fake = _FakeAsaas()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = _svc(s, fake)
        await svc.issue_bank_slip(inv.id)
        await svc.issue_nfe(inv.id)
        await svc.issue_nfe(inv.id)
    assert len(fake.invoices) == 1, "duas notas para a mesma fatura é problema contábil"


# ── releitura ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_reads_the_current_state(engine, app_session_factory, session):
    """Webhook se perde; sem releitura, fatura paga ficaria aberta para sempre."""
    t, inv = await _seed(session)
    fake = _FakeAsaas()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = _svc(s, fake)
        await svc.issue_bank_slip(inv.id)
        await svc.issue_nfe(inv.id)
        fake.payment_status = "RECEIVED"
        refreshed = await svc.refresh(inv.id)
    assert refreshed.asaas_charge_status == "RECEIVED"
    assert refreshed.nfe_status == "AUTHORIZED"
    assert refreshed.nfe_pdf_url == "https://asaas.test/nfe.pdf"


@pytest.mark.asyncio
async def test_refresh_on_an_uncharged_invoice_is_a_no_op(engine, app_session_factory, session):
    t, inv = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        # Sem cobrança, nem o cliente do Asaas é tocado — passar None prova.
        out = await _svc(s, None, enabled=False).refresh(inv.id)
    assert out.asaas_payment_id is None
