"""Portal /v1/notifications — Spec #3 V3.

Escopo por destinatário: a sessão só enxerga/marca como lida a notificação
cujo recipient_login é o customer_login do próprio cookie — nunca a de
outro usuário do mesmo tenant (404), nem de outro tenant (404, RLS).
Espelha o padrão de cookie+host de test_invoices_router.py.
"""

from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain.notification_service import NotificationService
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, ZnunyInstance

AURORA_HOST = {"host": "aurora.suporte.gerti.com.br"}


async def _seed_two_tenants(session):
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
    a = Tenant(
        legal_name="Aurora",
        trade_name="Aurora",
        document="1",
        znuny_customer_id="AURORA",
        znuny_instance_id=inst.id,
        subdomain="aurora",
    )
    b = Tenant(
        legal_name="Beta",
        trade_name="Beta",
        document="2",
        znuny_customer_id="BETA",
        znuny_instance_id=inst.id,
        subdomain="beta",
    )
    session.add_all([a, b])
    await session.commit()
    return a.id, b.id


@pytest.fixture
def _app(engine, app_session_factory, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    return create_app()


@pytest.mark.asyncio
async def test_no_cookie_401(_app, session):
    # tenant precisa existir p/ o TenantMiddleware resolver o subdomínio antes
    # da dependency de sessão (senão 404 de tenant desconhecido mascara o 401).
    await _seed_two_tenants(session)
    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://t") as c:
        assert (await c.get("/v1/notifications", headers=AURORA_HOST)).status_code == 401


@pytest.mark.asyncio
async def test_list_scoped_by_recipient_and_read_flow(_app, session, app_session_factory):
    a_id, b_id = await _seed_two_tenants(session)
    st = get_settings()

    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        svc = NotificationService(s)
        mine = await svc.emit(
            recipient_login="joe@aurora",
            kind="system",
            title="Minha notificação",
            at=dt.datetime(2026, 3, 1, tzinfo=dt.UTC),
        )
        await svc.emit(
            recipient_login="mary@aurora",
            kind="system",
            title="Notificação de outro usuário",
            at=dt.datetime(2026, 3, 1, tzinfo=dt.UTC),
        )
    # mesmo login, mas em outro tenant — nunca deve vazar para a sessão da Aurora
    async with db.tenant_session_scope(b_id, factory=app_session_factory) as s:
        cross_tenant = await NotificationService(s).emit(
            recipient_login="joe@aurora", kind="system", title="Notificação de outro tenant"
        )

    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(a_id), "joe@aurora", "helpdesk", st))

        # 200: só enxerga a própria (nem a de mary@aurora, nem a do tenant B)
        resp = await c.get("/v1/notifications", headers=AURORA_HOST)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["unread"] == 1
        assert body["items"][0]["title"] == "Minha notificação"
        assert body["limit"] == 20
        assert body["offset"] == 0

        # marcar a própria como lida -> 204
        resp2 = await c.post(f"/v1/notifications/{mine.id}/read", headers=AURORA_HOST)
        assert resp2.status_code == 204

        # 404 ao tentar marcar a notificação de outro destinatário do mesmo tenant
        async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
            marys = await NotificationService(s).list_for("mary@aurora")
        mary_notif_id = marys.items[0].id
        resp3 = await c.post(f"/v1/notifications/{mary_notif_id}/read", headers=AURORA_HOST)
        assert resp3.status_code == 404

        # 404 cross-tenant: id existe, mas em outro tenant (RLS esconde)
        resp4 = await c.post(f"/v1/notifications/{cross_tenant.id}/read", headers=AURORA_HOST)
        assert resp4.status_code == 404

        # read-all: já não há mais não-lidas da própria sessão
        resp5 = await c.post("/v1/notifications/read-all", headers=AURORA_HOST)
        assert resp5.status_code == 200
        assert resp5.json()["updated"] == 0

        # filtro status=unread devolve vazio após a leitura
        resp6 = await c.get("/v1/notifications?status=unread", headers=AURORA_HOST)
        assert resp6.status_code == 200
        assert resp6.json()["total"] == 0
