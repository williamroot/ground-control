"""V-R11.4/V-R11.5 — rotas da agenda de atividades recorrentes (R11).

Além do caminho feliz, dois negativos que importam:
  • forma incompatível com a frequência (semanal sem dia da semana) → 422 em
    português, antes do CHECK do banco;
  • tarefa de OUTRO cliente não é editável pela URL deste — a sessão é
    BYPASSRLS, então o `tenant_id` tem que ser conferido na mão.
"""

from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, ZnunyInstance

_HOST = {"host": "gerti.was.dev.br"}


def _settings(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    return get_settings()


async def _seed_two(session: AsyncSession) -> tuple[Tenant, Tenant]:
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
    out = []
    for name, sub, cid in (("Aurora", "aurora", "AURORA"), ("TechNova", "technova", "TECHNOVA")):
        t = Tenant(
            legal_name=name,
            trade_name=name,
            document="1",
            znuny_customer_id=cid,
            znuny_instance_id=inst.id,
            subdomain=sub,
        )
        session.add(t)
        out.append(t)
    await session.commit()
    return out[0], out[1]


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _setup(engine, session, monkeypatch):
    settings = _settings(monkeypatch)
    a, b = await _seed_two(session)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", factory)
    monkeypatch.setattr(db, "SessionLocal", factory)
    return settings, a, b, create_app()


def _body(**over):
    base = {
        "title": "Verificação de backup",
        "body": "Conferir o backup noturno.",
        "frequency": "weekly",
        "weekday": 0,
        "at_time": "08:00:00",
        "starts_on": "2026-08-01",
        "znuny_queue_name": "Preventivos",
        "customer_user_login": "mariana.bianchi",
        "active": True,
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_create_and_list_shows_the_next_occurrence(engine, session, monkeypatch):
    """T-R11.4 — "toda segunda, 08:00" com a próxima ocorrência à vista."""
    settings, a, _b, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.post(f"/v1/admin/tenants/{a.id}/recurring-tasks", headers=_HOST, json=_body())
        assert r.status_code == 201, r.text
        assert r.json()["schedule_label"] == "toda segunda-feira, 08:00"

        listed = await c.get(f"/v1/admin/tenants/{a.id}/recurring-tasks", headers=_HOST)
    assert listed.status_code == 200
    task = listed.json()[0]
    assert task["title"] == "Verificação de backup"
    # A próxima ocorrência é sempre uma segunda-feira no futuro.
    nxt = dt.date.fromisoformat(task["next_occurrence"])
    assert nxt.weekday() == 0
    assert nxt >= dt.datetime.now(dt.UTC).date()


@pytest.mark.asyncio
async def test_shape_must_match_frequency(engine, session, monkeypatch):
    settings, a, _b, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.post(
            f"/v1/admin/tenants/{a.id}/recurring-tasks",
            headers=_HOST,
            json=_body(frequency="weekly", weekday=None),
        )
        assert r.status_code == 422
        assert "dia da semana" in r.json()["detail"]

        r2 = await c.post(
            f"/v1/admin/tenants/{a.id}/recurring-tasks",
            headers=_HOST,
            json=_body(frequency="monthly", weekday=None, day_of_month=None),
        )
        assert r2.status_code == 422
        assert "dia do mês" in r2.json()["detail"]

        r3 = await c.post(
            f"/v1/admin/tenants/{a.id}/recurring-tasks",
            headers=_HOST,
            json=_body(starts_on="2026-08-10", ends_on="2026-08-01"),
        )
        assert r3.status_code == 422


@pytest.mark.asyncio
async def test_a_task_of_another_tenant_is_not_editable(engine, session, monkeypatch):
    """A sessão é BYPASSRLS: sem checagem explícita, a URL de A editaria B."""
    settings, a, b, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        created = await c.post(
            f"/v1/admin/tenants/{b.id}/recurring-tasks", headers=_HOST, json=_body()
        )
        task_id = created.json()["id"]
        r = await c.put(
            f"/v1/admin/tenants/{a.id}/recurring-tasks/{task_id}",
            headers=_HOST,
            json=_body(title="sequestrada"),
        )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_listing_never_leaks_another_tenant(engine, session, monkeypatch):
    settings, a, b, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        await c.post(
            f"/v1/admin/tenants/{a.id}/recurring-tasks",
            headers=_HOST,
            json=_body(title="Da Aurora"),
        )
        await c.post(
            f"/v1/admin/tenants/{b.id}/recurring-tasks",
            headers=_HOST,
            json=_body(title="Da TechNova"),
        )
        listed = await c.get(f"/v1/admin/tenants/{a.id}/recurring-tasks", headers=_HOST)
    assert [t["title"] for t in listed.json()] == ["Da Aurora"]


@pytest.mark.asyncio
async def test_agenda_lists_the_next_30_days(engine, session, monkeypatch):
    """T-R11.5 — a visão que o técnico usa."""
    settings, a, _b, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        await c.post(f"/v1/admin/tenants/{a.id}/recurring-tasks", headers=_HOST, json=_body())
        r = await c.get(f"/v1/admin/tenants/{a.id}/recurring-tasks/agenda?days=30", headers=_HOST)
    assert r.status_code == 200, r.text
    entries = r.json()
    assert len(entries) >= 4  # ~4 segundas em 30 dias
    assert all(dt.date.fromisoformat(e["date"]).weekday() == 0 for e in entries)
    # Ordenada por data — a agenda é uma linha do tempo.
    assert [e["date"] for e in entries] == sorted(e["date"] for e in entries)


@pytest.mark.asyncio
async def test_inactive_task_is_out_of_the_agenda(engine, session, monkeypatch):
    settings, a, _b, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        await c.post(
            f"/v1/admin/tenants/{a.id}/recurring-tasks", headers=_HOST, json=_body(active=False)
        )
        r = await c.get(f"/v1/admin/tenants/{a.id}/recurring-tasks/agenda", headers=_HOST)
    assert r.json() == []


@pytest.mark.asyncio
async def test_routes_require_an_agent_session(engine, session, monkeypatch):
    settings, a, _b, app = await _setup(engine, session, monkeypatch)
    paths = [
        ("GET", f"/v1/admin/tenants/{a.id}/recurring-tasks"),
        ("POST", f"/v1/admin/tenants/{a.id}/recurring-tasks"),
        ("GET", f"/v1/admin/tenants/{a.id}/recurring-tasks/agenda"),
    ]
    async with _client(app) as c:
        for m, p in paths:
            assert (await c.request(m, p, headers=_HOST, json={})).status_code == 401, p
    async with _client(app) as c2:
        c2.cookies.set("gsid", "cookie-de-cliente")
        for m, p in paths:
            assert (await c2.request(m, p, headers=_HOST, json={})).status_code == 401, p
    assert settings is not None
