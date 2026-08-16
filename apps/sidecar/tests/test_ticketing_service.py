from __future__ import annotations

import datetime as dt
import uuid

import pytest

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.ticketing_service import (
    ContractChoiceRequired,
    NoActiveContract,
    OpenTicketInput,
    QueueNotAllowed,
    TicketingService,
)
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import Contract, Tenant, TenantQueue, ZnunyInstance
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


# ── T-R5.3 — o chamado nasce na fila padrão do CLIENTE, não no 'Raw' ────────
#
# Até esta onda, `TicketCreate.pm:67` mandava tudo para a string fixa `'Raw'`:
# todo chamado de todo cliente caía no mesmo lugar, sem forma de configurar.


async def _with_queue(session, tenant, *, queue_id: int, name: str, default: bool) -> None:
    session.add(
        TenantQueue(
            tenant_id=tenant.id,
            znuny_queue_id=queue_id,
            znuny_queue_name=name,
            is_default=default,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_ticket_lands_in_tenant_default_queue(
    engine, app_session_factory, session, monkeypatch
):
    """V-R5.4 / aceite A5.2 — sem fila informada, vai para a padrão do cliente."""
    t = await _seed_tenant(session, n_contracts=1)
    await _with_queue(session, t, queue_id=3, name="Suporte::N1", default=True)

    seen: dict[str, object] = {}

    async def fake_create(**kw):
        seen.update(kw)
        return znuny_ticket.TicketCreated(101, "N101")

    monkeypatch.setattr(znuny_ticket, "create_ticket", fake_create)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
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

    assert seen["queue"] == "Suporte::N1"
    assert seen["queue"] != "Raw"


@pytest.mark.asyncio
async def test_tenant_without_queue_config_keeps_historic_behaviour(
    engine, app_session_factory, session, monkeypatch
):
    """Cliente sem configuração: mandamos `None` e o Perl mantém o `Raw` de sempre.

    Importa porque mudar a fila padrão altera onde chamados de um ambiente que
    já roda vão cair. Quem não configurou nada não pode ser movido por acidente.
    """
    t = await _seed_tenant(session, n_contracts=1)
    seen: dict[str, object] = {}

    async def fake_create(**kw):
        seen.update(kw)
        return znuny_ticket.TicketCreated(102, "N102")

    monkeypatch.setattr(znuny_ticket, "create_ticket", fake_create)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
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
    assert seen["queue"] is None


@pytest.mark.asyncio
async def test_queue_not_associated_is_rejected(engine, app_session_factory, session, monkeypatch):
    """V-R5.4 (negativo) — fila que o cliente não acessa é recusada, sem criar nada."""
    t = await _seed_tenant(session, n_contracts=1)
    await _with_queue(session, t, queue_id=3, name="Suporte::N1", default=True)

    monkeypatch.setattr(
        znuny_ticket,
        "create_ticket",
        lambda **kw: (_ for _ in ()).throw(AssertionError("não pode criar chamado")),
    )
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(QueueNotAllowed):
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
                    queue="Financeiro",
                ),
            )
