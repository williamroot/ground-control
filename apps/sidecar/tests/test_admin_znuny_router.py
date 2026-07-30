"""Router /v1/admin/znuny/* — capa de administração do Znuny (Spec #4, Blocos A/B).

Cobre: 401 sem gsid_adm; 404 de objeto fora da allowlist e de id malformado;
200/201 no caminho feliz com o cliente GI mockado (não bate na rede); 422
quando o GI rejeita (inclusive DefinitionCheck reprovando); e a invariante
"zero tabela nova / única escrita em `gerti` é a auditoria".
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_admin_objects as zao
from gerti_sidecar.main import create_app

_HOST = {"host": "gerti.was.dev.br"}

# Nomes que NUNCA podem existir como tabela no schema gerti — se um deles
# aparecer, alguém introduziu uma segunda fonte de verdade para config do
# Znuny, violando a regra desta spec.
_FORBIDDEN_TABLE_NAMES = {
    "znuny_queue",
    "znuny_sla",
    "znuny_service",
    "znuny_type",
    "znuny_state",
    "znuny_priority",
    "znuny_ci_class",
    "znuny_object",
    "znuny_object_cache",
    "ci_class_definition",
    "ci_class",
}


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    return get_settings()


def _wire(monkeypatch, engine, app_session_factory) -> async_sessionmaker[AsyncSession]:
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    return admin_factory


async def _client(monkeypatch, engine, app_session_factory, *, login: str = "william"):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    app = create_app()
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
    c.cookies.set("gsid_adm", encode_admin_session(login, st))
    return c


# --------------------------------------------------------------------------- #
# 401 sem sessão admin
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_requires_admin_session(engine, app_session_factory, monkeypatch):
    _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/v1/admin/znuny/objects/Queue", headers=_HOST)
        assert r.status_code == 401
        r = await c.post("/v1/admin/znuny/objects/Queue", headers=_HOST, json={"Name": "x"})
        assert r.status_code == 401
        r = await c.get("/v1/admin/znuny/ci-classes", headers=_HOST)
        assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 404 — objeto fora da allowlist / id malformado
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_unknown_object_is_404(engine, app_session_factory, monkeypatch):
    async with await _client(monkeypatch, engine, app_session_factory) as c:
        r = await c.get("/v1/admin/znuny/objects/Frobnicator", headers=_HOST)
        assert r.status_code == 404
        assert (
            await c.get("/v1/admin/znuny/objects/Frobnicator/1", headers=_HOST)
        ).status_code == 404
        assert (
            await c.post("/v1/admin/znuny/objects/Frobnicator", headers=_HOST, json={})
        ).status_code == 404
        assert (
            await c.put("/v1/admin/znuny/objects/Frobnicator/1", headers=_HOST, json={})
        ).status_code == 404


@pytest.mark.asyncio
async def test_malformed_id_is_404(engine, app_session_factory, monkeypatch):
    async with await _client(monkeypatch, engine, app_session_factory) as c:
        assert (await c.get("/v1/admin/znuny/objects/Queue/abc", headers=_HOST)).status_code == 404
        assert (
            await c.put("/v1/admin/znuny/objects/Queue/abc", headers=_HOST, json={})
        ).status_code == 404
        assert (
            await c.get("/v1/admin/znuny/ci-classes/abc/definition", headers=_HOST)
        ).status_code == 404
        assert (
            await c.put("/v1/admin/znuny/ci-classes/abc/definition", headers=_HOST, json={})
        ).status_code == 404
        # id negativo/decimal também não casa o regex numérico -> 404
        assert (await c.get("/v1/admin/znuny/objects/Queue/-1", headers=_HOST)).status_code == 404
        assert (await c.get("/v1/admin/znuny/objects/Queue/1.5", headers=_HOST)).status_code == 404


# --------------------------------------------------------------------------- #
# Caminho feliz — Bloco A (objetos)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_list_objects_happy(engine, app_session_factory, monkeypatch):
    async def fake_list(object_key, *, agent_login):
        assert object_key == "Queue"
        assert agent_login == "william"
        return zao.AdminObjectListResult(
            items=[{"ID": 1, "Name": "Suporte"}],
            support={"ValidList": [{"ID": 1, "Name": "valid"}]},
        )

    monkeypatch.setattr(zao, "object_list", fake_list)
    async with await _client(monkeypatch, engine, app_session_factory) as c:
        r = await c.get("/v1/admin/znuny/objects/Queue", headers=_HOST)
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == [{"ID": 1, "Name": "Suporte"}]
        assert body["support"]["ValidList"] == [{"ID": 1, "Name": "valid"}]


@pytest.mark.asyncio
async def test_get_object_happy(engine, app_session_factory, monkeypatch):
    async def fake_get(object_key, object_id, *, agent_login):
        assert object_key == "SLA"
        assert object_id == 7
        return {"ID": 7, "Name": "Gold"}

    monkeypatch.setattr(zao, "object_get", fake_get)
    async with await _client(monkeypatch, engine, app_session_factory) as c:
        r = await c.get("/v1/admin/znuny/objects/SLA/7", headers=_HOST)
        assert r.status_code == 200
        assert r.json() == {"ID": 7, "Name": "Gold"}


@pytest.mark.asyncio
async def test_create_object_happy_201_and_audits(engine, app_session_factory, monkeypatch):
    async def fake_add(object_key, fields, *, agent_login):
        assert object_key == "Type"
        assert fields == {"Name": "Incidente"}
        assert agent_login == "william"
        return {"ID": 5, "Name": "Incidente"}

    monkeypatch.setattr(zao, "object_add", fake_add)
    admin_factory = _wire(monkeypatch, engine, app_session_factory)
    async with await _client(monkeypatch, engine, app_session_factory) as c:
        r = await c.post("/v1/admin/znuny/objects/Type", headers=_HOST, json={"Name": "Incidente"})
        assert r.status_code == 201, r.text
        assert r.json() == {"ID": 5, "Name": "Incidente"}

    async with admin_factory() as s:
        row = (
            await s.execute(
                text(
                    "select entity, entity_id, action, actor_login from gerti.audit_log "
                    "where entity = 'znuny_type'"
                )
            )
        ).first()
    assert row is not None
    assert row[0] == "znuny_type"
    assert row[1] == "5"
    assert row[2] == "create"
    assert row[3] == "william"


@pytest.mark.asyncio
async def test_update_object_happy_200_and_audits(engine, app_session_factory, monkeypatch):
    async def fake_update(object_key, object_id, fields, *, agent_login):
        assert object_key == "Priority"
        assert object_id == 2
        assert fields == {"Name": "3 normal"}
        return {"ID": 2, "Name": "3 normal"}

    monkeypatch.setattr(zao, "object_update", fake_update)
    admin_factory = _wire(monkeypatch, engine, app_session_factory)
    async with await _client(monkeypatch, engine, app_session_factory) as c:
        r = await c.put(
            "/v1/admin/znuny/objects/Priority/2", headers=_HOST, json={"Name": "3 normal"}
        )
        assert r.status_code == 200
        assert r.json() == {"ID": 2, "Name": "3 normal"}

    async with admin_factory() as s:
        row = (
            await s.execute(
                text(
                    "select entity, entity_id, action from gerti.audit_log "
                    "where entity = 'znuny_priority'"
                )
            )
        ).first()
    assert row is not None
    assert row[1] == "2"
    assert row[2] == "update"


# --------------------------------------------------------------------------- #
# Caminho feliz — Bloco B (classes de CI)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_ci_classes_list_happy(engine, app_session_factory, monkeypatch):
    async def fake_list(*, agent_login):
        return [{"ID": 1, "Name": "Computer"}]

    monkeypatch.setattr(zao, "ci_class_list", fake_list)
    async with await _client(monkeypatch, engine, app_session_factory) as c:
        r = await c.get("/v1/admin/znuny/ci-classes", headers=_HOST)
        assert r.status_code == 200
        assert r.json() == {"items": [{"ID": 1, "Name": "Computer"}]}


@pytest.mark.asyncio
async def test_ci_class_definition_get_happy(engine, app_session_factory, monkeypatch):
    async def fake_get(class_id, *, agent_login):
        assert class_id == 1
        return {"ClassID": 1, "Definition": {"Pages": []}}

    monkeypatch.setattr(zao, "ci_class_definition_get", fake_get)
    async with await _client(monkeypatch, engine, app_session_factory) as c:
        r = await c.get("/v1/admin/znuny/ci-classes/1/definition", headers=_HOST)
        assert r.status_code == 200
        assert r.json() == {"ClassID": 1, "Definition": {"Pages": []}}


@pytest.mark.asyncio
async def test_ci_class_definition_set_happy_and_audits(engine, app_session_factory, monkeypatch):
    async def fake_set(class_id, definition, *, agent_login):
        assert class_id == 1
        assert definition == {"Pages": []}
        return {"DefinitionID": 9}

    monkeypatch.setattr(zao, "ci_class_definition_set", fake_set)
    admin_factory = _wire(monkeypatch, engine, app_session_factory)
    async with await _client(monkeypatch, engine, app_session_factory) as c:
        r = await c.put(
            "/v1/admin/znuny/ci-classes/1/definition", headers=_HOST, json={"Pages": []}
        )
        assert r.status_code == 200
        assert r.json() == {"DefinitionID": 9}

    async with admin_factory() as s:
        row = (
            await s.execute(
                text(
                    "select entity, entity_id, action from gerti.audit_log "
                    "where entity = 'znuny_ci_class'"
                )
            )
        ).first()
    assert row is not None
    assert row[1] == "1"
    assert row[2] == "update"


# --------------------------------------------------------------------------- #
# Erros do GI: 503 / 422 (inclusive DefinitionCheck reprovando)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_znuny_unavailable_maps_to_503(engine, app_session_factory, monkeypatch):
    async def fake_list(object_key, *, agent_login):
        raise zao.ZnunyUnavailable("timeout")

    monkeypatch.setattr(zao, "object_list", fake_list)
    async with await _client(monkeypatch, engine, app_session_factory) as c:
        r = await c.get("/v1/admin/znuny/objects/Queue", headers=_HOST)
        assert r.status_code == 503


@pytest.mark.asyncio
async def test_znuny_write_error_maps_to_422_with_message(engine, app_session_factory, monkeypatch):
    async def fake_add(object_key, fields, *, agent_login):
        raise zao.ZnunyWriteError("nome já usado por outra fila")

    monkeypatch.setattr(zao, "object_add", fake_add)
    async with await _client(monkeypatch, engine, app_session_factory) as c:
        r = await c.post("/v1/admin/znuny/objects/Queue", headers=_HOST, json={"Name": "dup"})
        assert r.status_code == 422
        assert r.json()["detail"] == "nome já usado por outra fila"


@pytest.mark.asyncio
async def test_definition_check_failure_maps_to_422_with_message(
    engine, app_session_factory, monkeypatch
):
    async def fake_set(class_id, definition, *, agent_login):
        raise zao.ZnunyWriteError("DefinitionCheck failed: campo obrigatório ausente")

    monkeypatch.setattr(zao, "ci_class_definition_set", fake_set)
    async with await _client(monkeypatch, engine, app_session_factory) as c:
        r = await c.put(
            "/v1/admin/znuny/ci-classes/1/definition",
            headers=_HOST,
            json={"Pages": "forma errada"},
        )
        assert r.status_code == 422
        assert "DefinitionCheck failed" in r.json()["detail"]


# --------------------------------------------------------------------------- #
# Invariante da spec: zero tabela nova, única escrita em `gerti` é a auditoria
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_no_new_table_and_only_audit_log_written(engine, app_session_factory, monkeypatch):
    async def fake_add(object_key, fields, *, agent_login):
        return {"ID": 42, **fields}

    async def fake_update(object_key, object_id, fields, *, agent_login):
        return {"ID": object_id, **fields}

    async def fake_def_set(class_id, definition, *, agent_login):
        return {"DefinitionID": 1}

    monkeypatch.setattr(zao, "object_add", fake_add)
    monkeypatch.setattr(zao, "object_update", fake_update)
    monkeypatch.setattr(zao, "ci_class_definition_set", fake_def_set)
    admin_factory = _wire(monkeypatch, engine, app_session_factory)

    async with admin_factory() as s:
        table_rows = (
            await s.execute(
                text(
                    "select table_name from information_schema.tables "
                    "where table_schema = 'gerti' order by table_name"
                )
            )
        ).all()
        table_names = {r[0] for r in table_rows}

    # Nenhuma tabela de config do Znuny foi criada por esta spec.
    assert table_names.isdisjoint(_FORBIDDEN_TABLE_NAMES)

    async def _row_counts(session) -> dict[str, int]:
        counts: dict[str, int] = {}
        for name in table_names:
            n = await session.scalar(text(f'select count(*) from gerti."{name}"'))
            counts[name] = int(n or 0)
        return counts

    async with admin_factory() as s:
        before = await _row_counts(s)

    async with await _client(monkeypatch, engine, app_session_factory) as c:
        assert (
            await c.post("/v1/admin/znuny/objects/Queue", headers=_HOST, json={"Name": "Nova Fila"})
        ).status_code == 201
        assert (
            await c.put(
                "/v1/admin/znuny/objects/Queue/42", headers=_HOST, json={"Name": "Fila Editada"}
            )
        ).status_code == 200
        assert (
            await c.put(
                "/v1/admin/znuny/ci-classes/1/definition", headers=_HOST, json={"Pages": []}
            )
        ).status_code == 200

    async with admin_factory() as s:
        after_table_rows = (
            await s.execute(
                text(
                    "select table_name from information_schema.tables "
                    "where table_schema = 'gerti' order by table_name"
                )
            )
        ).all()
        after_table_names = {r[0] for r in after_table_rows}
        after = await _row_counts(s)

    # zero tabela nova criada pelas escritas em runtime.
    assert after_table_names == table_names

    # a ÚNICA tabela com contagem alterada é audit_log; todas as outras
    # (inclusive tenants/contratos/etc.) permanecem intocadas por esta rota.
    changed = {name for name in table_names if after[name] != before[name]}
    assert changed == {"audit_log"}
    assert after["audit_log"] == before["audit_log"] + 3


# --------------------------------------------------------------------------- #
# Leitura de recurso inexistente é 404, não 422.
#
# A distinção importa na tela: 422 é a definição INVÁLIDA reprovada pelo
# DefinitionCheck (no PUT); 404 é "essa classe não existe". Confundir os dois faz
# o console mostrar erro de validação para um id que simplesmente não está lá.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_ci_class_definition_missing_is_404(
    engine, app_session_factory, monkeypatch
) -> None:
    async def _boom(*_a: object, **_k: object) -> dict[str, object]:
        raise zao.ZnunyWriteError("class not found")

    monkeypatch.setattr(zao, "ci_class_definition_get", _boom)
    c = await _client(monkeypatch, engine, app_session_factory)
    async with c:
        resp = await c.get("/v1/admin/znuny/ci-classes/999/definition")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "ci_class_not_found"


@pytest.mark.asyncio
async def test_get_object_missing_is_404(engine, app_session_factory, monkeypatch) -> None:
    async def _boom(*_a: object, **_k: object) -> dict[str, object]:
        raise zao.ZnunyWriteError("not found")

    monkeypatch.setattr(zao, "object_get", _boom)
    c = await _client(monkeypatch, engine, app_session_factory)
    async with c:
        resp = await c.get("/v1/admin/znuny/objects/Queue/999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "queue_not_found"
