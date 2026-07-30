"""Router /v1/admin/tenants/{id}/kb/articles — console CRUD (Spec #3 V1).

- sem gsid_adm → 401
- tenant inválido/inexistente → 404 tenant_not_found
- criar (201), listar, editar (PUT), status/visibility inválidos → 422
- deletar (204) + 404 no artigo já deletado
- console enxerga draft/internal (diferente do cliente) e NÃO conta views
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, ZnunyInstance


async def _seed_tenant(engine) -> uuid.UUID:
    admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with admin() as s:
        inst = ZnunyInstance(
            name="main",
            base_url="http://znuny",
            db_dsn_secret_ref="x",
            webservice_token_secret_ref="x",
            webhook_signing_secret_ref="x",
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
        return t.id


@pytest.mark.asyncio
async def test_admin_kb_crud(engine, app_session_factory, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    tid = await _seed_tenant(engine)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        base = f"/v1/admin/tenants/{tid}/kb/articles"

        # sem sessão -> 401
        assert (await c.get(base)).status_code == 401

        c.cookies.set("gsid_adm", encode_admin_session("william", get_settings()))

        # tenant inexistente -> 404
        ghost = f"/v1/admin/tenants/{uuid.uuid4()}/kb/articles"
        assert (await c.get(ghost)).status_code == 404

        # criar com visibility inválida -> 422
        bad_vis = await c.post(
            base,
            json={
                "title": "Título válido",
                "body_markdown": "conteúdo",
                "category": "rede",
                "tags": [],
                "visibility": "nope",
                "status": "draft",
            },
        )
        assert bad_vis.status_code == 422

        # criar com status inválido -> 422
        bad_status = await c.post(
            base,
            json={
                "title": "Título válido",
                "body_markdown": "conteúdo",
                "category": "rede",
                "tags": [],
                "visibility": "public",
                "status": "nope",
            },
        )
        assert bad_status.status_code == 422

        # título curto demais -> 422
        bad_title = await c.post(
            base,
            json={
                "title": "ab",
                "body_markdown": "conteúdo",
                "category": "rede",
                "tags": [],
                "visibility": "public",
                "status": "draft",
            },
        )
        assert bad_title.status_code == 422

        # criar válido (draft, internal) -> 201; console vê mesmo sem publicar
        created = await c.post(
            base,
            json={
                "title": "Como resetar senha",
                "summary": "resumo",
                "body_markdown": "# passo a passo",
                "category": "acessos",
                "tags": ["Senha", "senha", " Acesso "],
                "visibility": "internal",
                "status": "draft",
            },
        )
        assert created.status_code == 201
        payload = created.json()
        assert payload["slug"] == "como-resetar-senha"
        assert payload["tags"] == ["senha", "acesso"]  # normalizado
        assert payload["views"] == 0
        article_id = payload["id"]

        # listar
        lst = await c.get(base)
        assert lst.status_code == 200
        assert lst.json()["total"] == 1

        # filtro por status
        filtered = await c.get(base, params={"status": "published"})
        assert filtered.json()["total"] == 0

        # GET detalhe -> não incrementa views (console nunca conta)
        detail = await c.get(f"{base}/{article_id}")
        assert detail.status_code == 200
        assert detail.json()["views"] == 0

        # editar (PUT) — muda status/título; slug permanece
        upd = await c.put(
            f"{base}/{article_id}",
            json={
                "title": "Título totalmente novo",
                "summary": "novo resumo",
                "body_markdown": "novo conteúdo",
                "category": "acessos",
                "tags": [],
                "visibility": "public",
                "status": "published",
            },
        )
        assert upd.status_code == 200
        assert upd.json()["slug"] == "como-resetar-senha"
        assert upd.json()["title"] == "Título totalmente novo"
        assert upd.json()["status"] == "published"

        # editar artigo inexistente -> 404
        assert (
            await c.put(
                f"{base}/{uuid.uuid4()}",
                json={
                    "title": "x" * 10,
                    "body_markdown": "y",
                    "category": "rede",
                    "tags": [],
                    "visibility": "public",
                    "status": "draft",
                },
            )
        ).status_code == 404

        # deletar
        dele = await c.delete(f"{base}/{article_id}")
        assert dele.status_code == 204
        assert (await c.get(f"{base}/{article_id}")).status_code == 404

        # deletar de novo -> 404
        assert (await c.delete(f"{base}/{article_id}")).status_code == 404
