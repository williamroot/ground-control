"""Router /v1/admin/ai/* (#1N Task 5) — opt-in (404 quando off), agente-only.

Mocka o GI (znuny_ticket.agent_get_thread) e o cliente Ollama (via factory) —
sem rede real, sem Znuny real. Usa testcontainer Postgres (fixtures do conftest).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.ollama import OllamaUnavailable
from gerti_sidecar.integrations.znuny_ticket import AgentTicket, Article
from gerti_sidecar.main import create_app
from gerti_sidecar.routers import admin_ai


def _ticket() -> AgentTicket:
    return AgentTicket(
        znuny_ticket_id=42,
        ticket_number="2026060810000042",
        title="Impressora",
        state="open",
        customer_id="AURORA",
        articles=[
            Article(
                role="customer", author="Cli", created="t", subject="S", body="parou de imprimir"
            )
        ],
    )


class _FakeOllama:
    _model = "gpt-oss:120b"

    def __init__(self, reply="RESUMO", raises=None):
        self.reply = reply
        self.raises = raises

    async def chat(self, messages, *, reasoning_effort="low"):
        if self.raises:
            raise self.raises
        return self.reply


def _wire(monkeypatch, engine, app_session_factory, *, ai_enabled: bool, ollama):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("AI_FEATURES_ENABLED", "true" if ai_enabled else "false")
    monkeypatch.setenv("OLLAMA_API_KEY", "KEY" if ai_enabled else "")
    get_settings.cache_clear()

    async def fake_thread(*, znuny_ticket_id: int):
        return _ticket()

    monkeypatch.setattr(znuny_ticket, "agent_get_thread", fake_thread)
    monkeypatch.setattr(admin_ai, "get_ollama_client", lambda settings: ollama)
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)


@pytest.mark.asyncio
async def test_summarize_happy_and_auth(engine, app_session_factory, monkeypatch):
    _wire(monkeypatch, engine, app_session_factory, ai_enabled=True, ollama=_FakeOllama("RESUMO"))
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # sem sessão → 401
        r = await c.post("/v1/admin/ai/summarize", json={"ticket_id": 42})
        assert r.status_code == 401
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post("/v1/admin/ai/summarize", json={"ticket_id": 42})
        assert r.status_code == 200
        assert r.json()["text"] == "RESUMO"


@pytest.mark.asyncio
async def test_suggest_reply_happy(engine, app_session_factory, monkeypatch):
    _wire(
        monkeypatch,
        engine,
        app_session_factory,
        ai_enabled=True,
        ollama=_FakeOllama("Olá, [VERIFICAR]"),
    )
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post(
            "/v1/admin/ai/suggest-reply", json={"ticket_id": 42, "instruction": "seja breve"}
        )
        assert r.status_code == 200
        assert "[VERIFICAR]" in r.json()["text"]


@pytest.mark.asyncio
async def test_feature_off_is_404(engine, app_session_factory, monkeypatch):
    _wire(monkeypatch, engine, app_session_factory, ai_enabled=False, ollama=_FakeOllama())
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post("/v1/admin/ai/summarize", json={"ticket_id": 42})
        assert r.status_code == 404
        # e o GET /enabled reflete o kill-switch
        e = await c.get("/v1/admin/ai/enabled")
        assert e.status_code == 200
        assert e.json()["enabled"] is False


@pytest.mark.asyncio
async def test_enabled_endpoint_true(engine, app_session_factory, monkeypatch):
    _wire(monkeypatch, engine, app_session_factory, ai_enabled=True, ollama=_FakeOllama())
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        e = await c.get("/v1/admin/ai/enabled")
        assert e.status_code == 200
        assert e.json()["enabled"] is True


@pytest.mark.asyncio
async def test_ollama_unavailable_is_503(engine, app_session_factory, monkeypatch):
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
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post("/v1/admin/ai/summarize", json={"ticket_id": 42})
        assert r.status_code == 503
