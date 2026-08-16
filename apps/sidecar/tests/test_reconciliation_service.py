from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.reconciliation_service import NS_TIMEACCOUNTING, ReconciliationService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import (
    ConsumptionEvent,
    ConsumptionOrphan,
    ConsumptionSyncCursor,
    Contract,
    Tenant,
    TicketContractLink,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType


async def _seed(session):  # type: ignore[no-untyped-def]
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
        legal_name="Acme",
        trade_name="Acme",
        document="1",
        znuny_customer_id="ACME",
        znuny_instance_id=inst.id,
        subdomain="acme",
    )
    session.add(t)
    await session.flush()
    hb = Contract(
        tenant_id=t.id,
        code="HB",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=100,
        created_by="seed",
    )
    cb = Contract(
        tenant_id=t.id,
        code="CB",
        type=ContractType.credit_brl,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_amount_brl=10000,
        unit_price_brl=200,
        created_by="seed",
    )
    session.add_all([hb, cb])
    await session.flush()
    # ticket 19 -> hour_bank ; ticket 20 -> credit_brl
    session.add(
        TicketContractLink(
            znuny_ticket_id=19, contract_id=hb.id, tenant_id=t.id, linked_by_rule="seed"
        )
    )
    session.add(
        TicketContractLink(
            znuny_ticket_id=20, contract_id=cb.id, tenant_id=t.id, linked_by_rule="seed"
        )
    )
    session.add(ConsumptionSyncCursor(znuny_instance_id=inst.id, last_time_accounting_id=0))
    await session.commit()
    return inst, t, hb, cb


def _gi_with(entries):  # type: ignore[no-untyped-def]
    class _GI:
        async def time_accounting_since(self, *, since_id, limit=500):  # type: ignore[no-untyped-def]
            page = [e for e in entries if e.id > since_id][:limit]
            return znuny_ticket.TimeAccountingPage(
                entries=page,
                max_id=max([e.id for e in page], default=since_id),
            )

    return _GI()


@pytest.mark.asyncio
async def test_reconcile_converts_and_is_idempotent(  # type: ignore[no-untyped-def]
    engine, app_session_factory, session, monkeypatch
):
    inst, t, hb, cb = await _seed(session)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    entries = [
        znuny_ticket.TimeEntry(
            id=101, ticket_id=19, article_id=50, time_unit=30.0, created="2026-06-08 10:00:00"
        ),
        znuny_ticket.TimeEntry(
            id=102, ticket_id=20, article_id=60, time_unit=60.0, created="2026-06-08 11:00:00"
        ),
        # ticket 999 sem vínculo — deve ser ignorado
        znuny_ticket.TimeEntry(
            id=103, ticket_id=999, article_id=70, time_unit=15.0, created="2026-06-08 12:00:00"
        ),
    ]
    svc = ReconciliationService(gi=_gi_with(entries))
    n = await svc.reconcile()
    assert n == 2  # ticket 999 ignorado (sem vínculo)

    # idempotência: re-run não cria novos eventos
    n2 = await svc.reconcile()
    assert n2 == 0

    # verifica conversão sob o tenant
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        rows = (
            (await s.execute(select(ConsumptionEvent).order_by(ConsumptionEvent.id)))
            .scalars()
            .all()
        )
        assert len(rows) == 2
        hb_ev = next(r for r in rows if r.contract_id == hb.id)
        cb_ev = next(r for r in rows if r.contract_id == cb.id)
        assert float(hb_ev.billable_minutes) == 30.0
        assert float(hb_ev.billable_amount_brl) == 0.0  # hour_bank: sem BRL
        assert float(cb_ev.billable_minutes) == 60.0
        assert float(cb_ev.billable_amount_brl) == 200.0  # 60min/60 * 200 = 200
        # webhook_event_id determinístico
        assert hb_ev.webhook_event_id == uuid.uuid5(NS_TIMEACCOUNTING, "znuny:timeaccounting:101")

    # cursor avançou
    async with db.AdminSessionLocal() as a:
        cur = await a.get(ConsumptionSyncCursor, inst.id)
        assert cur.last_time_accounting_id == 103


@pytest.mark.asyncio
async def test_gi_unavailable_does_not_advance_cursor(  # type: ignore[no-untyped-def]
    engine, app_session_factory, session, monkeypatch
):
    # Patcha ANTES de qualquer uso de db.AdminSessionLocal
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    inst, t, hb, _cb = await _seed(session)

    # Seta cursor para 5 explicitamente (o _seed cria com 0)
    async with admin_factory() as a:
        cur = await a.get(ConsumptionSyncCursor, inst.id)
        cur.last_time_accounting_id = 5
        await a.commit()

    # GI stub que levanta ZnunyUnavailable
    class _DownGI:
        async def time_accounting_since(self, *, since_id, limit=500):  # type: ignore[no-untyped-def]
            raise znuny_ticket.ZnunyUnavailable("down")

    svc = ReconciliationService(gi=_DownGI())

    with pytest.raises(znuny_ticket.ZnunyUnavailable):
        await svc.reconcile()

    # Cursor deve continuar em 5 — não foi avançado
    async with admin_factory() as a:
        cur = await a.get(ConsumptionSyncCursor, inst.id)
        assert cur.last_time_accounting_id == 5


# ── T-R2.3 — hora em chamado SEM vínculo não pode sumir ─────────────────────
#
# O vínculo chamado↔contrato só nasce no POST do portal. Todo chamado que
# entrar por e-mail (R9, Onda 2) nasce sem ele — e, até esta onda, o worker
# descartava o lançamento em silêncio e ainda avançava o cursor por cima.
#
# Decisão D-E: o cursor CONTINUA avançando (é código financeiro vivo, e segurá-lo
# travaria a reconciliação inteira por causa de um órfão). O que muda é que o
# descarte deixa de ser silencioso.


async def _seed_one_contract(session):  # type: ignore[no-untyped-def]
    """Tenant com EXATAMENTE um contrato ativo e nenhum vínculo de chamado."""
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
        legal_name="Acme",
        trade_name="Acme",
        document="1",
        znuny_customer_id="ACME",
        znuny_instance_id=inst.id,
        subdomain="acme",
    )
    session.add(t)
    await session.flush()
    cb = Contract(
        tenant_id=t.id,
        code="CB",
        type=ContractType.credit_brl,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_amount_brl=10000,
        unit_price_brl=200,
        created_by="seed",
    )
    session.add(cb)
    session.add(ConsumptionSyncCursor(znuny_instance_id=inst.id, last_time_accounting_id=0))
    await session.commit()
    return inst, t, cb


@pytest.mark.asyncio
async def test_orphan_with_single_active_contract_is_linked_and_billed(  # type: ignore[no-untyped-def]
    engine, app_session_factory, session, monkeypatch
):
    """V-R2.3 / aceite A2.3 — 1 contrato ativo: vincula sozinho e a hora é faturada."""
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    _inst, t, cb = await _seed_one_contract(session)

    # Chamado 777 nunca passou pelo portal — é o cenário do e-mail.
    entries = [
        znuny_ticket.TimeEntry(
            id=201,
            ticket_id=777,
            article_id=None,
            time_unit=60.0,
            created="2026-08-15 09:00:00",
            customer_id="ACME",
            customer_user_id="ana@acme.example",
        )
    ]
    n = await ReconciliationService(gi=_gi_with(entries)).reconcile()
    assert n == 1, "a hora do chamado por e-mail precisa ser faturada, não descartada"

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        link = (
            await s.execute(
                select(TicketContractLink).where(TicketContractLink.znuny_ticket_id == 777)
            )
        ).scalar_one()
        assert link.contract_id == cb.id
        assert "auto-link" in link.linked_by_rule
        ev = (await s.execute(select(ConsumptionEvent))).scalars().one()
        assert float(ev.billable_minutes) == 60.0
        assert float(ev.billable_amount_brl) == 200.0

    # Nada foi para a fila de pendência.
    async with db.AdminSessionLocal() as a:
        assert (await a.execute(select(ConsumptionOrphan))).scalars().all() == []


@pytest.mark.asyncio
async def test_orphan_with_two_active_contracts_becomes_visible_pendency(  # type: ignore[no-untyped-def]
    engine, app_session_factory, session, monkeypatch
):
    """V-R2.3 (o caso ambíguo) — 2 contratos ativos: NADA é cobrado, e fica registrado.

    Escolher um dos dois por conta própria seria faturar no contrato errado —
    pior do que não faturar. A pendência é o que impede o silêncio.
    """
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    inst, t, _hb, _cb = await _seed(session)  # este seed tem DOIS contratos ativos

    entries = [
        znuny_ticket.TimeEntry(
            id=301,
            ticket_id=888,
            article_id=None,
            time_unit=45.0,
            created="2026-08-15 10:00:00",
            customer_id="ACME",
            customer_user_id="ana@acme.example",
        )
    ]
    n = await ReconciliationService(gi=_gi_with(entries)).reconcile()
    assert n == 0, "com 2 contratos ativos, nada pode ser debitado automaticamente"

    async with db.AdminSessionLocal() as a:
        orphan = (await a.execute(select(ConsumptionOrphan))).scalars().one()
        assert orphan.reason == "ambiguous_contract"
        assert orphan.znuny_ticket_id == 888
        assert orphan.znuny_customer_id == "ACME"
        assert orphan.tenant_id == t.id
        assert orphan.status == "pending"
        assert float(orphan.time_unit) == 45.0
        # D-E: o cursor avança mesmo assim — o registro é que troca o silêncio.
        cur = await a.get(ConsumptionSyncCursor, inst.id)
        assert cur.last_time_accounting_id == 301

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        assert (await s.execute(select(ConsumptionEvent))).scalars().all() == []
        assert (
            await s.execute(
                select(TicketContractLink).where(TicketContractLink.znuny_ticket_id == 888)
            )
        ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_orphan_from_unknown_customer_is_recorded_not_dropped(  # type: ignore[no-untyped-def]
    engine, app_session_factory, session, monkeypatch
):
    """CustomerID que não casa com nenhum cliente vira pendência `no_tenant`."""
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    await _seed_one_contract(session)

    entries = [
        znuny_ticket.TimeEntry(
            id=401,
            ticket_id=999,
            article_id=None,
            time_unit=10.0,
            created="2026-08-15 11:00:00",
            customer_id="EMPRESA-QUE-NAO-EXISTE",
        )
    ]
    assert await ReconciliationService(gi=_gi_with(entries)).reconcile() == 0

    async with db.AdminSessionLocal() as a:
        orphan = (await a.execute(select(ConsumptionOrphan))).scalars().one()
        assert orphan.reason == "no_tenant"
        assert orphan.tenant_id is None


@pytest.mark.asyncio
async def test_orphan_pendency_is_idempotent(  # type: ignore[no-untyped-def]
    engine, app_session_factory, session, monkeypatch
):
    """Rescan da mesma faixa não multiplica a pendência (unique por lançamento)."""
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    inst, _t, _hb, _cb = await _seed(session)

    entries = [
        znuny_ticket.TimeEntry(
            id=501,
            ticket_id=1001,
            article_id=None,
            time_unit=5.0,
            created="2026-08-15 12:00:00",
            customer_id="ACME",
        )
    ]
    svc = ReconciliationService(gi=_gi_with(entries))
    await svc.reconcile()
    # Rebobina o cursor à mão, como faria um reprocessamento manual.
    async with admin_factory() as a:
        cur = await a.get(ConsumptionSyncCursor, inst.id)
        cur.last_time_accounting_id = 500
        await a.commit()
    await svc.reconcile()

    async with admin_factory() as a:
        rows = (await a.execute(select(ConsumptionOrphan))).scalars().all()
        assert len(rows) == 1
