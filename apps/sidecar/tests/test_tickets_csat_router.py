"""Spec #1M Task 3 — router POST /v1/tickets/{id}/csat + estado csat no detalhe.

Padrão de teste de router (TestClient ASGI + TenantMiddleware + cookie gsid)
copiado de test_assets_router.py. GI (znuny_ticket.get_ticket) é monkeypatchado.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance


@dataclass
class _FakeTicket:
    znuny_ticket_id: int
    ticket_number: str = "TN-1"
    title: str = "T"
    state: str = "closed successful"
    priority: str = "3 normal"
    created: str = "2026-06-09"
    contract_id: str | None = None
    customer_id: str = "AURORA"
    articles: list[dict[str, object]] | None = None

    def __post_init__(self) -> None:
        if self.articles is None:
            self.articles = []


async def _seed_tenant(session) -> Tenant:
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
        legal_name="Aurora",
        trade_name="Aurora",
        document="1",
        znuny_customer_id="AURORA",
        znuny_instance_id=inst.id,
        subdomain="aurora",
    )
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name="Aurora"))
    await session.commit()
    return t


def _wire(monkeypatch, engine, app_session_factory, *, state: str = "closed successful"):
    async def fake_get_ticket(*, znuny_ticket_id: int, customer_id: str) -> _FakeTicket:
        return _FakeTicket(znuny_ticket_id=znuny_ticket_id, state=state)

    monkeypatch.setattr(znuny_ticket, "get_ticket", fake_get_ticket)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)


@pytest.mark.asyncio
async def test_csat_post_lifecycle(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed_tenant(session)
    _wire(monkeypatch, engine, app_session_factory, state="closed successful")
    app = create_app()
    st = get_settings()
    h = {"host": "aurora.suporte.gerti.com.br"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # 401 sem sessão
        assert (
            await c.post("/v1/tickets/10/csat", json={"score": 5}, headers=h)
        ).status_code == 401

        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))

        # detalhe: eligible (fechado e ainda sem resposta)
        d = await c.get("/v1/tickets/10", headers=h)
        assert d.status_code == 200
        assert d.json()["csat"] == {"submitted": False, "eligible": True}

        # POST nota 5 → 201
        r = await c.post(
            "/v1/tickets/10/csat",
            json={"score": 5, "comment": "ótimo"},
            headers=h,
        )
        assert r.status_code == 201
        assert r.json()["score"] == 5

        # repetir → 409
        r2 = await c.post("/v1/tickets/10/csat", json={"score": 4}, headers=h)
        assert r2.status_code == 409

        # detalhe agora mostra submitted + score
        d2 = await c.get("/v1/tickets/10", headers=h)
        assert d2.json()["csat"] == {"submitted": True, "score": 5}


@pytest.mark.asyncio
async def test_csat_open_ticket_422(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed_tenant(session)
    _wire(monkeypatch, engine, app_session_factory, state="open")
    app = create_app()
    st = get_settings()
    h = {"host": "aurora.suporte.gerti.com.br"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        # detalhe: não elegível (aberto)
        d = await c.get("/v1/tickets/20", headers=h)
        assert d.json()["csat"] == {"submitted": False, "eligible": False}
        # POST em ticket aberto → 422
        r = await c.post("/v1/tickets/20/csat", json={"score": 5}, headers=h)
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_csat_score_validation(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed_tenant(session)
    _wire(monkeypatch, engine, app_session_factory, state="closed successful")
    app = create_app()
    st = get_settings()
    h = {"host": "aurora.suporte.gerti.com.br"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        # score fora de 1..5 → 422 (validação do pydantic)
        assert (
            await c.post("/v1/tickets/30/csat", json={"score": 0}, headers=h)
        ).status_code == 422
        assert (
            await c.post("/v1/tickets/30/csat", json={"score": 6}, headers=h)
        ).status_code == 422
