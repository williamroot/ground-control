"""Router /v1/admin/timer/* — ciclo completo e guard de autenticação.

Monkeypatch GI (znuny_ticket.time_accounting_add) para não precisar de Znuny real.
Usa testcontainer Postgres via fixtures `engine`/`app_session_factory` do conftest.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.main import create_app


@pytest.mark.asyncio
async def test_timer_lifecycle_requires_admin(engine, app_session_factory, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    async def fake_add(**kw):
        return None

    monkeypatch.setattr(znuny_ticket, "time_accounting_add", fake_add)
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # sem gsid_adm → 401
        assert (
            await c.post("/v1/admin/timer/start", json={"znuny_ticket_id": 19})
        ).status_code == 401
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post("/v1/admin/timer/start", json={"znuny_ticket_id": 19})
        assert r.status_code == 201
        tid = r.json()["id"]
        assert (await c.post("/v1/admin/timer/pause", json={"timer_id": tid})).status_code == 200
        assert (await c.post("/v1/admin/timer/resume", json={"timer_id": tid})).status_code == 200
        s = await c.post("/v1/admin/timer/stop", json={"timer_id": tid, "adjust_minutes": 10})
        assert s.status_code == 200
        assert s.json()["status"] == "stopped"
        # active list
        a = await c.get("/v1/admin/timer/active")
        assert a.status_code == 200


@pytest.mark.asyncio
async def test_get_ticket_maps_to_snake_case(engine, app_session_factory, monkeypatch):
    """GET /v1/admin/tickets/{id} devolve snake_case (contrato do front #1J).

    Regressão: o GI Znuny devolve chaves capitalizadas (TicketID/Title/Articles);
    a página /atendimento/[id] consome snake_case. Sem o mapeamento o detalhe
    renderiza em branco e o timer 'Iniciar' quebra (znuny_ticket_id undefined).
    """
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    async def fake_agent_get(*, znuny_ticket_id: int):
        return {
            "TicketID": znuny_ticket_id,
            "TicketNumber": "2026051710000384",
            "Title": "Lentidão na VPN para acesso ao ERP",
            "State": "open",
            "Priority": "4 high",
            "CustomerID": "AURORA",
            "Owner": "rafael.tavares",
            "Created": "2026-05-13 09:15:00",
            "Articles": [
                {
                    "ArticleID": 111,
                    "From": "Eduardo Salvi",
                    "SenderType": "customer",
                    "Subject": "VPN lenta",
                    "Body": "A VPN está lenta.",
                    "CreateTime": "2026-05-13 09:15:00",
                }
            ],
        }

    monkeypatch.setattr(znuny_ticket, "agent_get", fake_agent_get)
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.get("/v1/admin/tickets/39")
        assert r.status_code == 200
        d = r.json()
        assert d["znuny_ticket_id"] == 39
        assert d["ticket_number"] == "2026051710000384"
        assert d["title"] == "Lentidão na VPN para acesso ao ERP"
        assert d["state"] == "open"
        assert d["priority"] == "4 high"
        assert d["customer_id"] == "AURORA"
        assert d["owner"] == "rafael.tavares"
        assert d["created"] == "2026-05-13 09:15:00"
        assert d["contract"] is None
        # artigos mantêm chaves capitalizadas que o componente da thread usa
        assert d["articles"][0]["From"] == "Eduardo Salvi"
        assert d["articles"][0]["SenderType"] == "customer"
        # não vaza chaves capitalizadas de topo (o bug original)
        assert "TicketID" not in d
        assert "Title" not in d
