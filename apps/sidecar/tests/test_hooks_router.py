"""Router POST /v1/hooks/znuny/ticket-event — HMAC + resolução de tenant.

- assinatura inválida → 401
- tenant não resolvido pelo customer_id → 202 (aceita e ignora, sem vazar)
- ok → 200 e processa (engine roda, automation_run gravado)
"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.webhook_sig import sign
from gerti_sidecar.main import create_app
from gerti_sidecar.models import AutomationRule, AutomationRun, Tenant, ZnunyInstance

SECRET = "shared-hmac-secret-for-tests"


async def _seed(engine, app_session_factory):
    """Cria instância (com segredo) + tenant + 1 regra. Retorna o customer_id."""
    admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with admin() as s:
        inst = ZnunyInstance(
            name="main",
            base_url="http://znuny",
            db_dsn_secret_ref="x",
            webservice_token_secret_ref="x",
            webhook_signing_secret_ref=SECRET,
            mode="pool",
        )
        s.add(inst)
        await s.flush()
        t = Tenant(
            legal_name="Aurora SA",
            trade_name="Aurora",
            document="1",
            znuny_customer_id="AURORA",
            znuny_instance_id=inst.id,
            subdomain="aurora",
        )
        s.add(t)
        await s.commit()
        tid = t.id
    # regra via RLS-subject
    async with app_session_factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tid)}
            )
            s.add(
                AutomationRule(
                    tenant_id=tid,
                    name="urgente",
                    trigger_event="article_create",
                    conditions=[{"field": "title", "op": "contains", "value": "urgente"}],
                    actions=[{"type": "set_priority", "params": {"priority": "5 very high"}}],
                    position=0,
                )
            )
    return tid


@pytest.mark.asyncio
async def test_hooks_flow(engine, app_session_factory, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    calls: list[dict] = []

    async def fake_update(**kw):
        calls.append(kw)

    monkeypatch.setattr(znuny_ticket, "agent_ticket_update", fake_update)

    tid = await _seed(engine, app_session_factory)

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://api-dev.was.dev.br"
    ) as c:
        payload = {
            "event": "article_create",
            "ticket_id": 99,
            "customer_id": "AURORA",
            "title": "Servidor urgente fora do ar",
            "state": "open",
        }
        body = json.dumps(payload).encode()

        # assinatura inválida → 401
        bad = await c.post(
            "/v1/hooks/znuny/ticket-event",
            content=body,
            headers={"content-type": "application/json", "x-gerti-signature": "sha256=deadbeef"},
        )
        assert bad.status_code == 401

        # tenant desconhecido → 202 (aceita e ignora)
        unknown = {**payload, "customer_id": "NOPE"}
        ub = json.dumps(unknown).encode()
        miss = await c.post(
            "/v1/hooks/znuny/ticket-event",
            content=ub,
            headers={"content-type": "application/json", "x-gerti-signature": sign(SECRET, ub)},
        )
        assert miss.status_code == 202

        # ok → 200 e processa
        ok = await c.post(
            "/v1/hooks/znuny/ticket-event",
            content=body,
            headers={"content-type": "application/json", "x-gerti-signature": sign(SECRET, body)},
        )
        assert ok.status_code == 200

    # a ação foi executada (prioridade elevada)
    assert calls == [{"ticket_id": 99, "priority": "5 very high"}]
    # automation_run matched=True gravado
    async with app_session_factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tid)}
            )
            runs = (await s.execute(select(AutomationRun))).scalars().all()
    assert len(runs) == 1 and runs[0].matched is True
