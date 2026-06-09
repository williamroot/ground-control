# apps/sidecar/tests/test_tickets_router.py
from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Contract, Tenant, TenantBranding, ZnunyInstance
from gerti_sidecar.models.enums import ContractType


async def _seed(session):
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
    session.add(TenantBranding(tenant_id=t.id, display_name="Acme"))
    contract = Contract(
        tenant_id=t.id,
        code="C-1",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=100,
        created_by="seed",
    )
    session.add(contract)
    await session.commit()
    return t


@pytest.mark.asyncio
async def test_open_ticket_single_contract(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)

    async def fake_create(**kw):
        return znuny_ticket.TicketCreated(123, "2026010100001")

    monkeypatch.setattr(znuny_ticket, "create_ticket", fake_create)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post(
            "/v1/tickets", headers=h, data={"title": "t", "body": "b"}
        )  # sem contract_id -> auto
        assert r.status_code == 201
        assert r.json()["ticket_number"] == "2026010100001"


@pytest.mark.asyncio
async def test_get_ticket_ownership(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)

    async def fake_get(*, znuny_ticket_id, customer_id):
        # cliente da empresa ACME tentando ler ticket de outra => GI levanta WriteError
        from gerti_sidecar.integrations.znuny_ticket import ZnunyWriteError

        raise ZnunyWriteError("ticket not found")

    monkeypatch.setattr(znuny_ticket, "get_ticket", fake_get)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.get("/v1/tickets/999", headers=h)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_reply_happy_path(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)

    async def fake_reply(**kw):
        return None

    monkeypatch.setattr(znuny_ticket, "reply_ticket", fake_reply)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post("/v1/tickets/5/reply", headers=h, json={"body": "oi"})
        assert r.status_code == 201
        assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_reply_ownership_404(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)

    from gerti_sidecar.integrations.znuny_ticket import ZnunyWriteError

    async def fake_reply(**kw):
        raise ZnunyWriteError("not found")

    monkeypatch.setattr(znuny_ticket, "reply_ticket", fake_reply)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post("/v1/tickets/5/reply", headers=h, json={"body": "oi"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_video_attachment_allowed(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)

    async def fake_create(**kw):
        assert kw["attachments"] and kw["attachments"][0].filename.endswith(".mp4")
        return znuny_ticket.TicketCreated(7, "N7")

    monkeypatch.setattr(znuny_ticket, "create_ticket", fake_create)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post(
            "/v1/tickets",
            headers=h,
            data={"title": "t", "body": "b"},
            files={"files": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")},
        )
        assert r.status_code == 201


@pytest.mark.asyncio
async def test_list_helpdesk_scope_own(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)

    async def fake_search(*, scope, customer_user, customer_id):
        assert scope == "own"
        return []

    monkeypatch.setattr(znuny_ticket, "search_tickets", fake_search)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.get("/v1/tickets", headers=h)
        assert r.status_code == 200
        assert r.json() == []
