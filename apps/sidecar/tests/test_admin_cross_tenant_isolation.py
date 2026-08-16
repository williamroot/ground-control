"""Isolamento entre clientes nas telas do CONSOLE — sob BYPASSRLS (Onda 3).

Invariante 6 da campanha: isolamento é **provado por teste**, nunca presumido.
Este arquivo existe porque a presunção quebrou na prática.

## O que quebrou, e por quê

As rotas de console abrem a sessão assim:

    tenant_session_scope(tid, factory=db.AdminSessionLocal)

Isso seta `app.current_tenant`… numa conexão de `gerti_admin_user`, que tem
**BYPASSRLS**. Em Postgres, uma role com BYPASSRLS **não** é submetida às
policies — o GUC é gravado e simplesmente ignorado. Toda consulta que dependia
só da RLS para se limitar ao tenant passava a enxergar a base inteira.

Foi achado na verificação ao vivo da Onda 3: a tela de consumo da **Aurora**
listava contratos da **TechNova**. O mesmo padrão já valia, de antes, para o
painel de analytics (`/v1/admin/analytics`), que soma horas e lista saldos.

A correção é sempre a mesma: filtrar por `tenant_id` **explicitamente** nas
rotas de console, tratando a RLS como segunda barreira e nunca como a única.

Estes testes rodam de propósito com a factory ADMIN (BYPASSRLS) — rodar com
`gerti_sidecar` provaria a RLS, que não é o caminho que falhou.
"""

from __future__ import annotations

import datetime as dt
import uuid

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


async def _seed_two(session: AsyncSession) -> tuple[Tenant, Tenant]:
    """Dois clientes, cada um com 1 contrato e consumo próprio no mesmo mês."""
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

    made: list[Tenant] = []
    for name, sub, cid, code, minutes in (
        ("Aurora", "aurora", "AURORA", "AUR-HORAS", 120.0),
        ("TechNova", "technova", "TECHNOVA", "TNV-HORAS", 600.0),
    ):
        t = Tenant(
            legal_name=name,
            trade_name=name,
            document="1",
            znuny_customer_id=cid,
            znuny_instance_id=inst.id,
            subdomain=sub,
        )
        session.add(t)
        await session.flush()
        session.add(TenantBranding(tenant_id=t.id, display_name=name))
        c = Contract(
            tenant_id=t.id,
            code=code,
            type=ContractType.hour_bank,
            starts_on=dt.date(2026, 1, 1),
            ends_on=dt.date(2026, 12, 31),
            initial_hours=100,
            created_by="seed",
        )
        session.add(c)
        await session.flush()
        # Dois eventos por cliente, com o MESMO tamanho, porque as duas telas
        # olham janelas diferentes: o relatório pede um mês fixo (2026-05) e o
        # painel de analytics olha os últimos 30 dias corridos.
        for when, ref in (
            (dt.datetime(2026, 5, 10, 9, tzinfo=dt.UTC), "mes-do-relatorio"),
            (dt.datetime.now(dt.UTC) - dt.timedelta(days=1), "janela-do-painel"),
        ):
            session.add(
                ConsumptionEvent(
                    contract_id=c.id,
                    occurred_at=when,
                    source_kind="ticket_work",
                    source_ref=f"znuny:ticket:{code}:{ref}",
                    billable_minutes=minutes,
                    billable_amount_brl=0.0,
                    recorded_by="seed",
                )
            )
        made.append(t)
    await session.commit()
    return made[0], made[1]


async def _setup(engine, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    settings = get_settings()
    aurora, technova = await _seed_two(session)
    # A factory ADMIN nos DOIS slots: é exatamente a montagem de produção do
    # console, e é ela que torna a RLS inoperante.
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", factory)
    monkeypatch.setattr(db, "SessionLocal", factory)

    async def fake_stats(*, customer_id, since, until, include_tickets=False):
        return _stats()

    monkeypatch.setattr(znuny_ticket, "ticket_stats", fake_stats)
    return settings, aurora, technova, create_app()


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_consumption_series_never_shows_another_tenant(engine, session, monkeypatch):
    """A tela de consumo da Aurora só pode mostrar contratos da Aurora."""
    settings, aurora, technova, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.get(
            f"/v1/admin/tenants/{aurora.id}/consumption-series?window=months&count=3",
            headers=_HOST,
        )
    assert r.status_code == 200, r.text
    codes = [s["code"] for s in r.json()["series"]]
    assert codes == ["AUR-HORAS"], f"vazou contrato de outro cliente: {codes}"


@pytest.mark.asyncio
async def test_monthly_report_never_shows_another_tenant(engine, session, monkeypatch):
    """O relatório é o pior lugar para vazar: ele vira PDF e vai para o cliente."""
    settings, aurora, technova, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.get(
            f"/v1/admin/tenants/{aurora.id}/reports/monthly?month=2026-05", headers=_HOST
        )
    assert r.status_code == 200, r.text
    body = r.json()
    codes = [x["code"] for x in body["consumption"]]
    assert codes == ["AUR-HORAS"], f"vazou contrato de outro cliente: {codes}"
    # 120 min da Aurora = 2 h. Se as 10 h da TechNova entrassem, daria 12.
    assert body["consumption"][0]["value"] == 2.0


@pytest.mark.asyncio
async def test_analytics_panel_never_shows_another_tenant(engine, session, monkeypatch):
    """Vazamento PRÉ-EXISTENTE (#1O), corrigido junto por ser a mesma causa.

    O painel somava as horas de todos os clientes e listava o saldo de todos os
    contratos, em qualquer `tenant_id` que se pedisse.
    """
    settings, aurora, technova, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.get(f"/v1/admin/analytics?tenant_id={aurora.id}", headers=_HOST)
    assert r.status_code == 200, r.text
    body = r.json()
    codes = [x["code"] for x in body["balance"]["contracts"]]
    assert codes == ["AUR-HORAS"], f"vazou contrato de outro cliente: {codes}"
    # 120 min da Aurora = 2 h; com a TechNova junto seriam 12.
    assert body["hours"]["total_hours"] == 2.0


@pytest.mark.asyncio
async def test_each_tenant_sees_its_own_numbers(engine, session, monkeypatch):
    """Controle positivo: a correção não zerou tudo — cada um vê o seu."""
    settings, aurora, technova, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        a = await c.get(f"/v1/admin/analytics?tenant_id={aurora.id}", headers=_HOST)
        t = await c.get(f"/v1/admin/analytics?tenant_id={technova.id}", headers=_HOST)
    assert a.json()["hours"]["total_hours"] == 2.0
    assert t.json()["hours"]["total_hours"] == 10.0
    assert [x["code"] for x in t.json()["balance"]["contracts"]] == ["TNV-HORAS"]


@pytest.mark.asyncio
async def test_unknown_tenant_still_404s(engine, session, monkeypatch):
    settings, _a, _t, app = await _setup(engine, session, monkeypatch)
    ghost = uuid.uuid4()
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        for path in (
            f"/v1/admin/tenants/{ghost}/consumption-series",
            f"/v1/admin/tenants/{ghost}/reports/monthly?month=2026-05",
            f"/v1/admin/analytics?tenant_id={ghost}",
        ):
            assert (await c.get(path, headers=_HOST)).status_code == 404, path
