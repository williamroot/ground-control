"""#1S Task 4 — POST /v1/ticketing/assist + ai_assist_enabled no form-meta.

Cliente-facing (gsid). Opt-in: AI_FEATURES_ENABLED off → 404 (feature oculta);
AiRateLimited → 429; OllamaUnavailable → 503; body vazio → 400; sem sessão → 401.
GET /v1/ticketing/form-meta inclui ai_assist_enabled (= settings flag).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.ollama import OllamaUnavailable
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance
from gerti_sidecar.routers import ticketing_meta

HOST = {"host": "acme.suporte.gerti.com.br"}


class _FakeOllama:
    _model = "gpt-oss:120b"

    def __init__(self, reply='{"title":"T","body":"B"}', raises=None):
        self.reply = reply
        self.raises = raises

    async def chat(self, messages, *, reasoning_effort="low"):
        if self.raises:
            raise self.raises
        return self.reply


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
    await session.commit()
    return t


def _wire(monkeypatch, engine, app_session_factory, *, ai_enabled: bool, ollama):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("AI_FEATURES_ENABLED", "true" if ai_enabled else "false")
    monkeypatch.setenv("OLLAMA_API_KEY", "KEY" if ai_enabled else "")
    get_settings.cache_clear()
    monkeypatch.setattr(ticketing_meta, "get_ollama_client", lambda settings: ollama)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)


@pytest.mark.asyncio
async def test_assist_happy_and_auth(engine, app_session_factory, session, monkeypatch):
    t = await _seed_tenant(session)
    _wire(monkeypatch, engine, app_session_factory, ai_enabled=True, ollama=_FakeOllama())
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # sem sessão → 401
        r = await c.post("/v1/ticketing/assist", json={"body": "nao imprime"}, headers=HOST)
        assert r.status_code == 401
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post(
            "/v1/ticketing/assist", json={"title": "x", "body": "nao imprime"}, headers=HOST
        )
        assert r.status_code == 200
        assert r.json() == {"title": "T", "body": "B"}


@pytest.mark.asyncio
async def test_assist_empty_body_is_400(engine, app_session_factory, session, monkeypatch):
    t = await _seed_tenant(session)
    _wire(monkeypatch, engine, app_session_factory, ai_enabled=True, ollama=_FakeOllama())
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post("/v1/ticketing/assist", json={"body": "   "}, headers=HOST)
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_assist_feature_off_is_404(engine, app_session_factory, session, monkeypatch):
    t = await _seed_tenant(session)
    _wire(monkeypatch, engine, app_session_factory, ai_enabled=False, ollama=_FakeOllama())
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post("/v1/ticketing/assist", json={"body": "nao imprime"}, headers=HOST)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_assist_unavailable_is_503(engine, app_session_factory, session, monkeypatch):
    t = await _seed_tenant(session)
    _wire(
        monkeypatch,
        engine,
        app_session_factory,
        ai_enabled=True,
        ollama=_FakeOllama(raises=OllamaUnavailable("503")),
    )
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post("/v1/ticketing/assist", json={"body": "nao imprime"}, headers=HOST)
        assert r.status_code == 503


@pytest.mark.asyncio
async def test_assist_rate_limit_is_429(engine, app_session_factory, session, monkeypatch):
    from gerti_sidecar.domain.ai_service import ASSIST_RATE_LIMIT
    from gerti_sidecar.models import AiGenerationLog

    t = await _seed_tenant(session)
    for _ in range(ASSIST_RATE_LIMIT):
        session.add(
            AiGenerationLog(
                agent_login="joe",
                znuny_ticket_id=0,
                kind="assist",
                model="gpt-oss:120b",
                duration_ms=1,
                ok=True,
            )
        )
    await session.commit()
    _wire(monkeypatch, engine, app_session_factory, ai_enabled=True, ollama=_FakeOllama())
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post("/v1/ticketing/assist", json={"body": "nao imprime"}, headers=HOST)
        assert r.status_code == 429


@pytest.mark.asyncio
async def test_form_meta_includes_ai_assist_enabled(
    engine, app_session_factory, session, monkeypatch
):
    t = await _seed_tenant(session)
    _wire(monkeypatch, engine, app_session_factory, ai_enabled=True, ollama=_FakeOllama())

    async def fake_form_meta(**kw):
        return {"services": [], "priorities": [], "types": []}

    monkeypatch.setattr(znuny_ticket, "form_meta", fake_form_meta)
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.get("/v1/ticketing/form-meta", headers=HOST)
        assert r.status_code == 200
        assert r.json()["ai_assist_enabled"] is True
