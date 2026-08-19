"""R7 na ROTA — a lição da Onda 1, aplicada de novo.

Naquela onda a guarda de fila passava no serviço e era **código morto** na
rota, porque o campo do formulário nunca chegava. Teste de serviço verde não
prova rota.

Aqui o risco é outro e igualmente invisível em teste de serviço: `/approvals`
declarada DEPOIS de `/{ticket_id}` faria o FastAPI casar
`/v1/tickets/approvals` com a rota do chamado (`ticket_id: int`) e devolver
422 — a fila do portal nunca carregaria, com todo o domínio funcionando.
"""

from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.approval_service import ApprovalService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Contract, Tenant, TenantBranding, ZnunyInstance
from gerti_sidecar.models.enums import ContractType

HOST = {"host": "acme.suporte.gerti.com.br"}


async def _seed(session, *, approval_required=True):
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
    session.add(TenantBranding(tenant_id=t.id, display_name="Acme"))
    session.add(
        Contract(
            tenant_id=t.id,
            code="C-1",
            type=ContractType.hour_bank,
            starts_on=dt.date(2026, 1, 1),
            ends_on=dt.date(2026, 12, 31),
            initial_hours=100,
            created_by="seed",
        )
    )
    await session.commit()
    return t


def _wire(monkeypatch, engine, app_session_factory):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)


@pytest.mark.asyncio
async def test_approvals_route_is_not_swallowed_by_the_ticket_id_route(
    engine, app_session_factory, session, monkeypatch
):
    """`/v1/tickets/approvals` tem de ser a fila, não `ticket_id="approvals"`."""
    _wire(monkeypatch, engine, app_session_factory)
    t = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await ApprovalService(s, znuny_ticket).open_pending(
            tenant_id=t.id, znuny_ticket_id=4242, requested_by="ana"
        )

    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "chefe", "approver", st))
        r = await c.get("/v1/tickets/approvals", headers=HOST)

    assert r.status_code == 200, f"a rota foi engolida por /{{ticket_id}}: {r.status_code}"
    assert [row["znuny_ticket_id"] for row in r.json()] == [4242]


@pytest.mark.asyncio
async def test_the_approver_decides_through_the_route(
    engine, app_session_factory, session, monkeypatch
):
    _wire(monkeypatch, engine, app_session_factory)
    t = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await ApprovalService(s, znuny_ticket).open_pending(
            tenant_id=t.id, znuny_ticket_id=555, requested_by="ana"
        )

    updates: list[dict] = []

    async def fake_update(**kw):
        updates.append(kw)

    monkeypatch.setattr(znuny_ticket, "agent_ticket_update", fake_update)
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "chefe", "approver", st))
        r = await c.post("/v1/tickets/555/approval", headers=HOST, json={"decision": "approved"})
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

        # Segunda decisão: 409 na rota, não sobrescrita.
        again = await c.post(
            "/v1/tickets/555/approval",
            headers=HOST,
            json={"decision": "rejected", "reason": "mudei de ideia"},
        )
    assert again.status_code == 409
    assert len(updates) == 1


@pytest.mark.asyncio
async def test_helpdesk_gets_403_from_the_route(engine, app_session_factory, session, monkeypatch):
    _wire(monkeypatch, engine, app_session_factory)
    t = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await ApprovalService(s, znuny_ticket).open_pending(
            tenant_id=t.id, znuny_ticket_id=777, requested_by="ana"
        )

    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "ana", "helpdesk", st))
        r = await c.post("/v1/tickets/777/approval", headers=HOST, json={"decision": "approved"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_rejecting_without_a_reason_is_422_at_the_route(
    engine, app_session_factory, session, monkeypatch
):
    _wire(monkeypatch, engine, app_session_factory)
    t = await _seed(session)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        await ApprovalService(s, znuny_ticket).open_pending(
            tenant_id=t.id, znuny_ticket_id=888, requested_by="ana"
        )

    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "chefe", "approver", st))
        r = await c.post("/v1/tickets/888/approval", headers=HOST, json={"decision": "rejected"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_opening_a_ticket_reports_the_pending_approval(
    engine, app_session_factory, session, monkeypatch
):
    """Aceite A7.1 — o autor precisa saber que o chamado está esperando alguém."""
    _wire(monkeypatch, engine, app_session_factory)
    t = await _seed(session, approval_required=True)

    created: list[dict] = []

    async def fake_create(**kw):
        created.append(kw)
        return znuny_ticket.TicketCreated(999, "2026010100999")

    monkeypatch.setattr(znuny_ticket, "create_ticket", fake_create)
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "ana", "helpdesk", st))
        r = await c.post("/v1/tickets", headers=HOST, data={"title": "t", "body": "b"})

    assert r.status_code == 201
    assert r.json()["approval"] == "pending"
    # E o estado de espera foi mandado ao Znuny — não é só marcação local.
    assert created[0]["state"] == "aguardando aprovacao"


@pytest.mark.asyncio
async def test_without_the_flag_the_ticket_opens_normally(
    engine, app_session_factory, session, monkeypatch
):
    _wire(monkeypatch, engine, app_session_factory)
    t = await _seed(session, approval_required=False)

    created: list[dict] = []

    async def fake_create(**kw):
        created.append(kw)
        return znuny_ticket.TicketCreated(1000, "2026010101000")

    monkeypatch.setattr(znuny_ticket, "create_ticket", fake_create)
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "ana", "helpdesk", st))
        r = await c.post("/v1/tickets", headers=HOST, data={"title": "t", "body": "b"})

    assert r.status_code == 201
    assert r.json()["approval"] is None
    assert created[0]["state"] is None
