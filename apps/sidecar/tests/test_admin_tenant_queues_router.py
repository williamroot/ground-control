"""/v1/admin/tenants/{id}/queues — relacionamentos cliente↔fila (R5, Onda 1).

*"Aqui a gente vai falar quais filas de atendimento o cara vai ter acesso.
Então a gente tem uma fila padrão."* (04:03)

O que estes testes protegem:
  • V-R5.1  associar filas, com uma marcada como padrão, e ler de volta
  • V-R5.2  fila inexistente no Znuny → 422 e **nenhuma** linha gravada;
            zero ou duas padrões → 422
  • A5.5    a tela sabe dizer quem atende cada fila (grupo do Znuny)
  • idempotência do PUT e a troca de padrão de A para B, que é onde o índice
    parcial único morde se a ordem das escritas estiver errada
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_admin_objects as zao
from gerti_sidecar.main import create_app
from gerti_sidecar.models import TenantQueue, ZnunyInstance
from tests.test_admin_tenants import _GISpy, _onboard_body

_HOST = {"host": "gerti.was.dev.br"}

# Filas "vivas" no Znuny de mentira: 3 Suporte::N1, 5 IMAC, 7 Preventivo.
_LIVE_QUEUES = [
    {"ID": 3, "Name": "Suporte::N1", "GroupID": 2, "ValidID": 1},
    {"ID": 5, "Name": "IMAC", "GroupID": 2, "ValidID": 1},
    {"ID": 7, "Name": "Preventivo", "GroupID": 4, "ValidID": 1},
]
_GROUPS = {"2": "suporte", "4": "campo"}


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    return get_settings()


class _QueueSpy:
    """Substitui a lista viva de filas do Znuny, e conta as idas ao GI."""

    def __init__(self, items=None, groups=None) -> None:
        self.items = _LIVE_QUEUES if items is None else items
        self.groups = _GROUPS if groups is None else groups
        self.calls = 0

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _list(object_key, *, agent_login):
            self.calls += 1
            assert object_key == "Queue"
            return zao.AdminObjectListResult(
                items=list(self.items), support={"GroupList": dict(self.groups)}
            )

        monkeypatch.setattr(zao, "object_list", _list)


async def _seed_instance(session: AsyncSession) -> None:
    session.add(
        ZnunyInstance(
            name="main",
            base_url="http://znuny",
            db_dsn_secret_ref="x",
            webservice_token_secret_ref="x",
            webhook_signing_secret_ref="x",
            mode="pool",
        )
    )
    await session.commit()


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _setup(engine, session, monkeypatch, *, queue_spy: _QueueSpy | None = None):
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", factory)
    monkeypatch.setattr(db, "SessionLocal", factory)
    _GISpy().install(monkeypatch)
    spy = queue_spy or _QueueSpy()
    spy.install(monkeypatch)
    return settings, spy, create_app()


async def _tenant(c, settings) -> str:
    c.cookies.set("gsid_adm", encode_admin_session("william", settings))
    r = await c.post("/v1/admin/tenants", headers=_HOST, json=_onboard_body())
    assert r.status_code == 201, r.text
    return str(r.json()["tenant"]["id"])


@pytest.mark.asyncio
async def test_associate_queues_with_one_default(engine, session, monkeypatch):
    """V-R5.1 / aceite A5.1 — duas filas associadas, a padrão só numa delas."""
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        tid = await _tenant(c, settings)
        r = await c.put(
            f"/v1/admin/tenants/{tid}/queues",
            headers=_HOST,
            json={"queues": [{"queue_id": 3, "is_default": True}, {"queue_id": 5}]},
        )
        assert r.status_code == 200, r.text
        got = await c.get(f"/v1/admin/tenants/{tid}/queues", headers=_HOST)

    queues = {q["queue_id"]: q for q in got.json()["queues"]}
    assert set(queues) == {3, 5}
    assert queues[3]["is_default"] is True
    assert queues[5]["is_default"] is False
    assert queues[3]["queue_name"] == "Suporte::N1"
    # A5.5 — quem atende: grupo resolvido a partir da lista viva.
    assert queues[3]["group_name"] == "suporte"


@pytest.mark.asyncio
async def test_unknown_queue_rejects_whole_set(engine, session, monkeypatch):
    """V-R5.2 / aceite A5.3 — fila que não existe no Znuny: 422 e nada gravado.

    Gravar as válidas e ignorar a inválida seria pior: o operador acharia que
    configurou três filas quando configurou duas.
    """
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        tid = await _tenant(c, settings)
        r = await c.put(
            f"/v1/admin/tenants/{tid}/queues",
            headers=_HOST,
            json={
                "queues": [
                    {"queue_id": 3, "is_default": True},
                    {"queue_id": 999},
                ]
            },
        )
    assert r.status_code == 422, r.text
    assert "999" in r.text

    rows = (await session.execute(select(TenantQueue))).scalars().all()
    assert rows == [], "nenhuma linha pode ter sido gravada"


@pytest.mark.asyncio
async def test_default_marking_must_be_exactly_one(engine, session, monkeypatch):
    """V-R5.2 — zero padrões e duas padrões são igualmente recusadas."""
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        tid = await _tenant(c, settings)

        nenhuma = await c.put(
            f"/v1/admin/tenants/{tid}/queues",
            headers=_HOST,
            json={"queues": [{"queue_id": 3}, {"queue_id": 5}]},
        )
        assert nenhuma.status_code == 422, nenhuma.text

        duas = await c.put(
            f"/v1/admin/tenants/{tid}/queues",
            headers=_HOST,
            json={
                "queues": [
                    {"queue_id": 3, "is_default": True},
                    {"queue_id": 5, "is_default": True},
                ]
            },
        )
        assert duas.status_code == 422, duas.text

    assert (await session.execute(select(TenantQueue))).scalars().all() == []


@pytest.mark.asyncio
async def test_put_is_idempotent_and_can_move_the_default(engine, session, monkeypatch):
    """Mesmo conjunto → mesmo estado; e mover o padrão de 3 para 5 não colide.

    O índice parcial único (`ux_tenant_queue_default`) recusa duas padrões no
    mesmo cliente. Se a gravação marcasse a nova antes de limpar a antiga, esta
    troca estouraria — daí o teste existir.
    """
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    body = {"queues": [{"queue_id": 3, "is_default": True}, {"queue_id": 5}]}
    async with _client(app) as c:
        tid = await _tenant(c, settings)
        await c.put(f"/v1/admin/tenants/{tid}/queues", headers=_HOST, json=body)
        again = await c.put(f"/v1/admin/tenants/{tid}/queues", headers=_HOST, json=body)
        assert again.status_code == 200, again.text

        moved = await c.put(
            f"/v1/admin/tenants/{tid}/queues",
            headers=_HOST,
            json={"queues": [{"queue_id": 3}, {"queue_id": 5, "is_default": True}]},
        )
        assert moved.status_code == 200, moved.text

    rows = (await session.execute(select(TenantQueue))).scalars().all()
    assert len(rows) == 2, "reexecutar o mesmo PUT não pode duplicar linha"
    assert {r.znuny_queue_id: r.is_default for r in rows} == {3: False, 5: True}


@pytest.mark.asyncio
async def test_empty_selection_clears_the_configuration(engine, session, monkeypatch):
    """Lista vazia é o caminho de volta: o cliente deixa de ter filas associadas."""
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        tid = await _tenant(c, settings)
        await c.put(
            f"/v1/admin/tenants/{tid}/queues",
            headers=_HOST,
            json={"queues": [{"queue_id": 3, "is_default": True}]},
        )
        r = await c.put(f"/v1/admin/tenants/{tid}/queues", headers=_HOST, json={"queues": []})
        assert r.status_code == 200, r.text
        assert r.json()["queues"] == []

    assert (await session.execute(select(TenantQueue))).scalars().all() == []


@pytest.mark.asyncio
async def test_queues_of_unknown_tenant_is_404(engine, session, monkeypatch):
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        ghost = "11111111-2222-3333-4444-555555555555"
        assert (await c.get(f"/v1/admin/tenants/{ghost}/queues", headers=_HOST)).status_code == 404
        r = await c.put(
            f"/v1/admin/tenants/{ghost}/queues",
            headers=_HOST,
            json={"queues": [{"queue_id": 3, "is_default": True}]},
        )
        assert r.status_code == 404, r.text
        assert (
            await c.get("/v1/admin/tenants/nao-e-uuid/queues", headers=_HOST)
        ).status_code == 404


@pytest.mark.asyncio
async def test_listing_survives_znuny_down(engine, session, monkeypatch):
    """Znuny fora: a tela ainda mostra as filas associadas, pelo nome denormalizado."""
    settings, spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        tid = await _tenant(c, settings)
        await c.put(
            f"/v1/admin/tenants/{tid}/queues",
            headers=_HOST,
            json={"queues": [{"queue_id": 3, "is_default": True}]},
        )

        async def _down(object_key, *, agent_login):
            raise zao.ZnunyUnavailable("down")

        monkeypatch.setattr(zao, "object_list", _down)
        got = await c.get(f"/v1/admin/tenants/{tid}/queues", headers=_HOST)

    assert got.status_code == 200, got.text
    q = got.json()["queues"][0]
    assert q["queue_id"] == 3
    assert q["queue_name"] == "Suporte::N1"  # veio do denormalizado
    assert q["group_name"] is None  # o enriquecimento é que se perde
    assert spy.calls >= 1


@pytest.mark.asyncio
async def test_live_rename_wins_over_denormalized_name(engine, session, monkeypatch):
    """Renomear a fila no Znuny não pode deixar a tela mostrando o nome velho."""
    spy = _QueueSpy()
    settings, _s, app = await _setup(engine, session, monkeypatch, queue_spy=spy)
    async with _client(app) as c:
        tid = await _tenant(c, settings)
        await c.put(
            f"/v1/admin/tenants/{tid}/queues",
            headers=_HOST,
            json={"queues": [{"queue_id": 3, "is_default": True}]},
        )
        spy.items = [{"ID": 3, "Name": "Suporte::Nivel 1", "GroupID": 2, "ValidID": 1}]
        got = await c.get(f"/v1/admin/tenants/{tid}/queues", headers=_HOST)

    assert got.json()["queues"][0]["queue_name"] == "Suporte::Nivel 1"
