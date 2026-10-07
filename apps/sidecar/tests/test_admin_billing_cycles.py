"""GET /v1/admin/tenants/{id}/billing-cycles — ciclos fechados para faturar (T2).

O console pedia o UUID de um ciclo para gerar a fatura, e ninguém de fora
consegue fornecer isso. Esta rota lista os ciclos FECHADOS do tenant — com
`uninvoiced=true`, só os que ainda não têm fatura — e o total que a fatura
daria, pelo MESMO cálculo de `POST /invoices` (o teste confere os dois).

Escopo estrito por tenant: ciclo de outro tenant nunca aparece, tenant
inexistente é 404.
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
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.main import create_app
from gerti_sidecar.models import ContractCycle, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import ContractType, CycleKind, CycleStatus


async def _tenant(session, subdomain: str) -> Tenant:
    inst = ZnunyInstance(
        name=f"i-{subdomain}",
        base_url="http://z",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    t = Tenant(
        legal_name=subdomain,
        trade_name=subdomain,
        document=subdomain,
        znuny_customer_id=subdomain.upper(),
        znuny_instance_id=inst.id,
        subdomain=subdomain,
    )
    session.add(t)
    await session.commit()
    return t


def _cycle(contract_id: uuid.UUID, month: int, status: CycleStatus) -> ContractCycle:
    start = dt.date(2026, month, 1)
    end = dt.date(2026, month + 1, 1) - dt.timedelta(days=1)
    return ContractCycle(
        contract_id=contract_id,
        kind=CycleKind.closing,
        period_start=start,
        period_end=end,
        status=status,
        closed_at=None
        if status == CycleStatus.open
        else dt.datetime.combine(end, dt.time.max, tzinfo=dt.UTC),
    )


async def _seed(session, app_session_factory):
    aurora = await _tenant(session, "aurora")
    other = await _tenant(session, "outra")
    async with db.tenant_session_scope(aurora.id, factory=app_session_factory) as s:
        c = await ContractService(s).create(
            NewContract(
                code="AUR-PACOTE-2026",
                type=ContractType.closed_value,
                starts_on=dt.date(2026, 1, 1),
                ends_on=dt.date(2026, 12, 31),
                initial_amount_brl=160,
                created_by="seed",
            )
        )
        jul = _cycle(c.id, 7, CycleStatus.closed)
        aug = _cycle(c.id, 8, CycleStatus.closed)
        sep = _cycle(c.id, 9, CycleStatus.open)
        s.add_all([jul, aug, sep])
        await s.flush()
        ids = {"jul": jul.id, "aug": aug.id, "sep": sep.id, "contract": c.id}
    async with db.tenant_session_scope(other.id, factory=app_session_factory) as s:
        oc = await ContractService(s).create(
            NewContract(
                code="OUT-1",
                type=ContractType.closed_value,
                starts_on=dt.date(2026, 1, 1),
                ends_on=dt.date(2026, 12, 31),
                initial_amount_brl=999,
                created_by="seed",
            )
        )
        foreign = _cycle(oc.id, 8, CycleStatus.closed)
        s.add(foreign)
        await s.flush()
        ids["foreign"] = foreign.id
    return aurora, other, ids


def _wire(monkeypatch, engine, app_session_factory):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)


@pytest.mark.asyncio
async def test_billing_cycles_lists_closed_cycles_of_the_tenant_only(
    engine, app_session_factory, session, monkeypatch
):
    _wire(monkeypatch, engine, app_session_factory)
    aurora, _other, ids = await _seed(session, app_session_factory)
    base = f"/v1/admin/tenants/{aurora.id}"

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        # sem gsid_adm → 401
        assert (await c.get(f"{base}/billing-cycles")).status_code == 401
        c.cookies.set("gsid_adm", encode_admin_session("william", get_settings()))

        r = await c.get(f"{base}/billing-cycles")
        assert r.status_code == 200, r.text
        body = r.json()
        # Só os FECHADOS, do mais recente para o mais antigo; o aberto (set) e o
        # ciclo do outro tenant nunca aparecem.
        assert [x["id"] for x in body] == [str(ids["aug"]), str(ids["jul"])]
        assert str(ids["foreign"]) not in {x["id"] for x in body}
        first = body[0]
        assert first == {
            "id": str(ids["aug"]),
            "contract_id": str(ids["contract"]),
            "contract_code": "AUR-PACOTE-2026",
            "period_start": "2026-08-01",
            "period_end": "2026-08-31",
            "total_cents": 16000,
        }

        # Fatura o ciclo de julho: o total gerado é o que a lista prometia.
        inv = await c.post(f"{base}/invoices", json={"cycle_id": str(ids["jul"])})
        assert inv.status_code == 201, inv.text
        promised = {x["id"]: x["total_cents"] for x in body}
        assert inv.json()["total_cents"] == promised[str(ids["jul"])]

        # uninvoiced=true exclui o ciclo já faturado.
        r = await c.get(f"{base}/billing-cycles", params={"uninvoiced": "true"})
        assert r.status_code == 200
        assert [x["id"] for x in r.json()] == [str(ids["aug"])]

        # Sem o filtro, o faturado continua listado.
        r = await c.get(f"{base}/billing-cycles")
        assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_billing_cycles_unknown_tenant_is_404(
    engine, app_session_factory, session, monkeypatch
):
    _wire(monkeypatch, engine, app_session_factory)
    await _seed(session, app_session_factory)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", get_settings()))
        r = await c.get(f"/v1/admin/tenants/{uuid.uuid4()}/billing-cycles")
        assert r.status_code == 404
        r = await c.get("/v1/admin/tenants/not-a-uuid/billing-cycles")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_billing_cycles_of_the_other_tenant_stay_there(
    engine, app_session_factory, session, monkeypatch
):
    _wire(monkeypatch, engine, app_session_factory)
    aurora, other, ids = await _seed(session, app_session_factory)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", get_settings()))
        r = await c.get(f"/v1/admin/tenants/{other.id}/billing-cycles?uninvoiced=true")
        assert r.status_code == 200
        body = r.json()
        assert [x["id"] for x in body] == [str(ids["foreign"])]
        assert body[0]["contract_code"] == "OUT-1"
        assert body[0]["total_cents"] == 99900
        assert not {str(ids["jul"]), str(ids["aug"])} & {x["id"] for x in body}
