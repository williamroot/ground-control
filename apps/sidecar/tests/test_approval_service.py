"""R7 — aprovação de chamados (Onda 5).

*"Todo ticket passa, quando essa chave tá habilitada, todo ticket passa por
aqui e vai pra um aprovador."* (07:40)

Os quatro comportamentos que importam, e por quê:

1. **O chamado nasce em estado REAL de espera**, não criado-e-escondido. Se
   existisse normal e só sumisse do portal, um agente pegaria e atenderia algo
   que o cliente ainda não autorizou.
2. **A decisão é única** — segunda chamada é 409, não sobrescrita silenciosa.
3. **Reprovar exige motivo.** Sem ele, o cliente fica sem saber o que fazer a
   seguir e o histórico sem explicação.
4. **Quem não é aprovador não decide**, e chamado de outro cliente é 404 —
   nunca 403, que confirmaria a existência.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.approval_service import (
    PENDING_STATE,
    AlreadyDecided,
    ApprovalError,
    ApprovalNotFound,
    ApprovalService,
    NotAllowed,
)
from gerti_sidecar.domain.ticketing_service import OpenTicketInput, TicketingService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import Contract, Tenant, TicketApproval, ZnunyInstance
from gerti_sidecar.models.enums import ContractType, PortalRole

D = dt.date


class _GI:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.updated: list[dict] = []

    async def create_ticket(self, **kw):
        self.created.append(kw)
        return znuny_ticket.TicketCreated(700 + len(self.created), "N700")

    async def agent_ticket_update(self, **kw):
        self.updated.append(kw)


async def _seed(session, *, approval_required=True) -> Tenant:
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
        approval_required=approval_required,
    )
    session.add(t)
    await session.flush()
    session.add(
        Contract(
            tenant_id=t.id,
            code="C-1",
            type=ContractType.hour_bank,
            starts_on=D(2026, 1, 1),
            ends_on=D(2026, 12, 31),
            initial_hours=100,
            created_by="seed",
        )
    )
    await session.commit()
    return t


def _open_input(**over):
    base = dict(
        customer_user="ana",
        customer_id="ACME",
        title="Preciso de acesso",
        body="b",
        service=None,
        type_=None,
        priority=None,
        contract_id=None,
        attachments=[],
    )
    base.update(over)
    return OpenTicketInput(**base)


@pytest.mark.asyncio
async def test_ticket_is_born_waiting_not_hidden(engine, app_session_factory, session):
    """O estado é REAL no Znuny — nunca 'criado e escondido'."""
    t = await _seed(session)
    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        out = await TicketingService(s, gi).open_ticket(_open_input(requires_approval=True))
    assert out.approval == "pending"
    # O estado foi mandado ao Znuny, não só marcado no nosso banco.
    assert gi.created[0]["state"] == PENDING_STATE

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        row = (await s.execute(select(TicketApproval))).scalars().one()
    assert row.status == "pending"
    assert row.requested_by == "ana"


@pytest.mark.asyncio
async def test_without_the_flag_nothing_changes(engine, app_session_factory, session):
    """Cliente que não exige aprovação abre chamado como sempre."""
    t = await _seed(session, approval_required=False)
    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        out = await TicketingService(s, gi).open_ticket(_open_input())
        rows = (await s.execute(select(TicketApproval))).scalars().all()
    assert out.approval is None
    assert gi.created[0]["state"] is None
    assert rows == []


@pytest.mark.asyncio
async def test_approving_moves_the_ticket_and_is_final(engine, app_session_factory, session):
    t = await _seed(session)
    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        out = await TicketingService(s, gi).open_ticket(_open_input(requires_approval=True))
        svc = ApprovalService(s, gi)
        approved = await svc.decide(
            znuny_ticket_id=out.znuny_ticket_id,
            decision="approved",
            approver_login="chefe",
            approver_role=PortalRole.approver,
        )
        assert approved.status == "approved"
        assert approved.approver_login == "chefe"
        # O chamado saiu da espera no Znuny.
        assert gi.updated[-1]["state"] == "open"

        # Segunda decisão: 409, nunca sobrescrita silenciosa.
        with pytest.raises(AlreadyDecided):
            await svc.decide(
                znuny_ticket_id=out.znuny_ticket_id,
                decision="rejected",
                approver_login="outro",
                approver_role=PortalRole.admin,
                reason="mudei de ideia",
            )


@pytest.mark.asyncio
async def test_rejecting_requires_a_reason_and_closes_the_ticket(
    engine, app_session_factory, session
):
    t = await _seed(session)
    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        out = await TicketingService(s, gi).open_ticket(_open_input(requires_approval=True))
        svc = ApprovalService(s, gi)

        with pytest.raises(ApprovalError):
            await svc.decide(
                znuny_ticket_id=out.znuny_ticket_id,
                decision="rejected",
                approver_login="chefe",
                approver_role=PortalRole.approver,
                reason="   ",
            )
        # Nada foi decidido nem mexido no Znuny.
        assert gi.updated == []

        rejected = await svc.decide(
            znuny_ticket_id=out.znuny_ticket_id,
            decision="rejected",
            approver_login="chefe",
            approver_role=PortalRole.approver,
            reason="fora do escopo do contrato",
        )
    assert rejected.status == "rejected"
    assert rejected.reason == "fora do escopo do contrato"
    # O motivo vai para o próprio chamado: o cliente precisa poder LER por que
    # o pedido dele não passou, sem depender de alguém contar.
    assert "fora do escopo" in gi.updated[-1]["note"]
    assert gi.updated[-1]["state"] == "closed unsuccessful"


@pytest.mark.asyncio
async def test_helpdesk_cannot_decide(engine, app_session_factory, session):
    t = await _seed(session)
    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        out = await TicketingService(s, gi).open_ticket(_open_input(requires_approval=True))
        with pytest.raises(NotAllowed):
            await ApprovalService(s, gi).decide(
                znuny_ticket_id=out.znuny_ticket_id,
                decision="approved",
                approver_login="ana",
                approver_role=PortalRole.helpdesk,
            )
    assert gi.updated == []


@pytest.mark.asyncio
async def test_admin_can_decide_too(engine, app_session_factory, session):
    """Em empresa pequena o aprovador é o próprio admin do portal."""
    t = await _seed(session)
    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        out = await TicketingService(s, gi).open_ticket(_open_input(requires_approval=True))
        approved = await ApprovalService(s, gi).decide(
            znuny_ticket_id=out.znuny_ticket_id,
            decision="approved",
            approver_login="dono",
            approver_role=PortalRole.admin,
        )
    assert approved.status == "approved"


@pytest.mark.asyncio
async def test_deciding_an_unknown_ticket_is_not_found(engine, app_session_factory, session):
    t = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        with pytest.raises(ApprovalNotFound):
            await ApprovalService(s, _GI()).decide(
                znuny_ticket_id=999999,
                decision="approved",
                approver_login="chefe",
                approver_role=PortalRole.approver,
            )


@pytest.mark.asyncio
async def test_opening_twice_keeps_one_pending(engine, app_session_factory, session):
    """Idempotente: o mesmo chamado não gera duas pendências."""
    t = await _seed(session)
    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        svc = ApprovalService(s, gi)
        first = await svc.open_pending(tenant_id=t.id, znuny_ticket_id=555, requested_by="ana")
        second = await svc.open_pending(tenant_id=t.id, znuny_ticket_id=555, requested_by="ana")
        assert first.id == second.id
        rows = (await s.execute(select(TicketApproval))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_the_queue_only_lists_this_tenant(engine, app_session_factory, session):
    """RLS escopa a fila — o portal de um cliente não vê pendência de outro."""
    a = await _seed(session)
    gi = _GI()
    async with tenant_session_scope(a.id, factory=app_session_factory) as s:
        await ApprovalService(s, gi).open_pending(
            tenant_id=a.id, znuny_ticket_id=800, requested_by="ana"
        )
    async with tenant_session_scope(a.id, factory=app_session_factory) as s:
        pending = await ApprovalService(s, gi).pending_for_tenant()
    assert [p.znuny_ticket_id for p in pending] == [800]
