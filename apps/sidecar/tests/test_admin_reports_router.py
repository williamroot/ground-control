"""V-R18b.4 / V-R18a.4 — rotas de relatório e de consumo no console (Onda 3).

O teste que mais importa aqui é o do aceite **A18b.6**, e ele existe porque a
resposta certa não é óbvia: com o Znuny fora do ar, o **JSON degrada** (a tela
mostra o aviso) e o **PDF recusa** (503). O PDF é o artefato que sai da empresa
e vai para o cliente; um documento incompleto com cara de completo é o mesmo
modo de falha que a campanha vem combatendo desde a Onda 0. A regra fica
travada aqui, não deixada ao acaso.
"""

from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.main import create_app
from gerti_sidecar.models import (
    ConsumptionEvent,
    Contract,
    Tenant,
    TenantBranding,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType
from tests.test_report_service import _stats

_HOST = {"host": "gerti.was.dev.br"}
_GHOST = "11111111-2222-3333-4444-555555555555"


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    return get_settings()


async def _seed(session: AsyncSession) -> Tenant:
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
    session.add(TenantBranding(tenant_id=t.id, display_name="Acme Suporte"))
    c = Contract(
        tenant_id=t.id,
        code="C-1",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=100,
        created_by="seed",
    )
    session.add(c)
    await session.flush()
    session.add(
        ConsumptionEvent(
            contract_id=c.id,
            occurred_at=dt.datetime(2026, 5, 10, 9, tzinfo=dt.UTC),
            source_kind="ticket_work",
            source_ref="znuny:ticket:1",
            billable_minutes=120.0,
            billable_amount_brl=0.0,
            recorded_by="seed",
        )
    )
    await session.commit()
    return t


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _setup(engine, session, monkeypatch, *, down: bool = False):
    settings = _settings(monkeypatch)
    t = await _seed(session)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", factory)
    monkeypatch.setattr(db, "SessionLocal", factory)

    async def fake_stats(*, customer_id, since, until, include_tickets=False):
        if down:
            raise znuny_ticket.ZnunyUnavailable("timeout")
        return _stats()

    monkeypatch.setattr(znuny_ticket, "ticket_stats", fake_stats)
    return settings, t, create_app()


# ── relatório: conteúdo e formato ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_monthly_json(engine, session, monkeypatch):
    settings, t, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.get(f"/v1/admin/tenants/{t.id}/reports/monthly?month=2026-05", headers=_HOST)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["month_label"] == "maio/2026"
    assert body["display_name"] == "Acme Suporte"
    assert body["consumption"][0]["kind"] == "hours"
    assert body["consumption"][0]["value"] == 2.0
    assert body["ticket_total"] == 3
    assert len(body["tickets"]) == 3
    assert body["degraded"] is False


@pytest.mark.asyncio
async def test_monthly_pdf_is_a_pdf(engine, session, monkeypatch):
    """A18b.1 — o corpo é PDF de verdade, com o tipo de conteúdo certo."""
    settings, t, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.get(
            f"/v1/admin/tenants/{t.id}/reports/monthly.pdf?month=2026-05", headers=_HOST
        )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF-")
    assert len(r.content) > 1024
    assert "relatorio-2026-05" in r.headers.get("content-disposition", "")


# ── A18b.6: a decisão travada ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_degrades_when_znuny_is_down(engine, session, monkeypatch):
    settings, t, app = await _setup(engine, session, monkeypatch, down=True)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.get(f"/v1/admin/tenants/{t.id}/reports/monthly?month=2026-05", headers=_HOST)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["degraded"] is True
    assert body["tickets"] == []
    # O consumo sobrevive — ele vem do NOSSO banco, não do Znuny.
    assert body["consumption"][0]["value"] == 2.0


@pytest.mark.asyncio
async def test_pdf_refuses_when_znuny_is_down(engine, session, monkeypatch):
    """O PDF NÃO sai pela metade: 503 com motivo, nunca documento incompleto."""
    settings, t, app = await _setup(engine, session, monkeypatch, down=True)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.get(
            f"/v1/admin/tenants/{t.id}/reports/monthly.pdf?month=2026-05", headers=_HOST
        )
    assert r.status_code == 503, r.text
    assert "incompleto" in r.json()["detail"]
    assert not r.content.startswith(b"%PDF-")


# ── negativos: mês, tenant, autorização ────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_month_is_422(engine, session, monkeypatch):
    """A18b.5 — `2026-13` é recusado nas duas rotas."""
    settings, t, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        for path in ("monthly", "monthly.pdf"):
            r = await c.get(f"/v1/admin/tenants/{t.id}/reports/{path}?month=2026-13", headers=_HOST)
            assert r.status_code == 422, (path, r.text)


@pytest.mark.asyncio
async def test_unknown_tenant_is_404(engine, session, monkeypatch):
    settings, _t, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.get(f"/v1/admin/tenants/{_GHOST}/reports/monthly?month=2026-05", headers=_HOST)
        assert r.status_code == 404, r.text
        r2 = await c.get(
            "/v1/admin/tenants/nao-e-uuid/reports/monthly?month=2026-05", headers=_HOST
        )
        assert r2.status_code == 404, r2.text


@pytest.mark.asyncio
async def test_report_routes_require_an_agent_session(engine, session, monkeypatch):
    """V-R18b.4 — sem cookie de agente, 401. Cookie de cliente também não vale."""
    settings, t, app = await _setup(engine, session, monkeypatch)
    paths = [
        f"/v1/admin/tenants/{t.id}/reports/monthly?month=2026-05",
        f"/v1/admin/tenants/{t.id}/reports/monthly.pdf?month=2026-05",
        f"/v1/admin/tenants/{t.id}/consumption-series",
    ]
    async with _client(app) as c:  # sem cookie
        for p in paths:
            assert (await c.get(p, headers=_HOST)).status_code == 401, p
    async with _client(app) as c2:
        c2.cookies.set("gsid", "cookie-de-cliente-nao-serve")
        for p in paths:
            assert (await c2.get(p, headers=_HOST)).status_code == 401, p
    assert settings is not None


# ── V-R18a.4 — a rota de consumo por cliente ───────────────────────────────


@pytest.mark.asyncio
async def test_consumption_series_route(engine, session, monkeypatch):
    """A18a.1 — o agente escolhe o cliente NO CONSOLE e vê a série."""
    settings, t, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.get(
            f"/v1/admin/tenants/{t.id}/consumption-series?window=months&count=3",
            headers=_HOST,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window"] == "months"
    assert body["count"] == 3
    assert len(body["series"]) == 1
    s = body["series"][0]
    assert s["code"] == "C-1"
    assert s["kind"] == "hours"  # A18a.2 — a unidade vem junto de cada série
    assert len(s["points"]) == 3


@pytest.mark.asyncio
async def test_consumption_series_defaults_to_the_configured_window(engine, session, monkeypatch):
    """S3 — sem `?window=`, vale a chave `CONSUMPTION_WINDOW_MODE`."""
    monkeypatch.setenv("CONSUMPTION_WINDOW_MODE", "months")
    monkeypatch.setenv("CONSUMPTION_WINDOW_COUNT", "6")
    settings, t, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.get(f"/v1/admin/tenants/{t.id}/consumption-series", headers=_HOST)
    body = r.json()
    assert body["window"] == "months"
    assert body["count"] == 6
    assert len(body["series"][0]["points"]) == 6


@pytest.mark.asyncio
async def test_consumption_series_unknown_tenant_is_404(engine, session, monkeypatch):
    settings, _t, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        assert (
            await c.get(f"/v1/admin/tenants/{_GHOST}/consumption-series", headers=_HOST)
        ).status_code == 404
