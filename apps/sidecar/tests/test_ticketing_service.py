from __future__ import annotations

import datetime as dt
import uuid

import pytest

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.ticketing_service import (
    ContractChoiceRequired,
    NoActiveContract,
    OpenTicketInput,
    TicketingService,
)
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import Contract, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import ContractType


async def _seed_tenant(session, *, n_contracts: int) -> Tenant:
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
    for i in range(n_contracts):
        session.add(
            Contract(
                tenant_id=t.id,
                code=f"C-{i}",
                type=ContractType.hour_bank,
                starts_on=dt.date(2026, 1, 1),
                ends_on=dt.date(2026, 12, 31),
                initial_hours=100,
                created_by="seed",
            )
        )
    await session.commit()
    return t


@pytest.mark.asyncio
async def test_auto_selects_single_contract(engine, app_session_factory, session, monkeypatch):
    t = await _seed_tenant(session, n_contracts=1)

    async def fake_create(**kw):
        assert kw["contract_id"]  # auto-selected
        return znuny_ticket.TicketCreated(99, "N99")

    monkeypatch.setattr(znuny_ticket, "create_ticket", fake_create)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        out = await TicketingService(s, znuny_ticket).open_ticket(
            OpenTicketInput(
                customer_user="joe",
                customer_id="ACME",
                title="t",
                body="b",
                service=None,
                type_=None,
                priority=None,
                contract_id=None,
                attachments=[],
            ),
        )
        assert out.znuny_ticket_id == 99


@pytest.mark.asyncio
async def test_requires_choice_when_multiple(engine, app_session_factory, session, monkeypatch):
    t = await _seed_tenant(session, n_contracts=2)
    monkeypatch.setattr(
        znuny_ticket,
        "create_ticket",
        lambda **kw: (_ for _ in ()).throw(AssertionError("must not create")),
    )
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(ContractChoiceRequired):
            await TicketingService(s, znuny_ticket).open_ticket(
                OpenTicketInput(
                    customer_user="joe",
                    customer_id="ACME",
                    title="t",
                    body="b",
                    service=None,
                    type_=None,
                    priority=None,
                    contract_id=None,
                    attachments=[],
                ),
            )


@pytest.mark.asyncio
async def test_unknown_contract_rejected(engine, app_session_factory, session, monkeypatch):
    t = await _seed_tenant(session, n_contracts=2)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(NoActiveContract):
            await TicketingService(s, znuny_ticket).open_ticket(
                OpenTicketInput(
                    customer_user="joe",
                    customer_id="ACME",
                    title="t",
                    body="b",
                    service=None,
                    type_=None,
                    priority=None,
                    contract_id=str(uuid.uuid4()),
                    attachments=[],
                ),
            )
