"""Router /v1/admin/tenants/{id}/kb/articles — instrumentação de auditoria (Spec #3 V5).

Achado da revisão adversarial: `admin_kb.py`/`admin_catalog.py` faziam escrita
sem nunca chamar `audit_service.record` — buraco na trilha de auditoria.
Este teste cobre a instrumentação do KB (o padrão é o mesmo do catálogo):

- criar artigo grava uma linha em `audit_log` (entity="kb_article", action="create")
- falha real na gravação da auditoria (ex.: DB indisponível) NÃO impede a
  criação do artigo — a operação principal segue normalmente (201).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain import audit_service
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, ZnunyInstance
from gerti_sidecar.models.audit_log import AuditLog


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    return get_settings()


async def _seed_tenant(engine, *, subdomain: str = "aurora-audit") -> uuid.UUID:
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
            document=subdomain,
            znuny_customer_id=subdomain.upper(),
            znuny_instance_id=inst.id,
            subdomain=subdomain,
        )
        s.add(t)
        await s.commit()
        return t.id


def _wire(monkeypatch, engine, app_session_factory) -> async_sessionmaker[AsyncSession]:
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    return admin_factory


@pytest.mark.asyncio
async def test_create_kb_article_writes_audit_row(engine, app_session_factory, monkeypatch):
    st = _settings(monkeypatch)
    admin_factory = _wire(monkeypatch, engine, app_session_factory)
    tid = await _seed_tenant(engine)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        base = f"/v1/admin/tenants/{tid}/kb/articles"

        created = await c.post(
            base,
            json={
                "title": "Como solicitar acesso à VPN",
                "summary": "resumo",
                "body_markdown": "# passo a passo",
                "category": "acessos",
                "tags": [],
                "visibility": "internal",
                "status": "draft",
            },
        )
        assert created.status_code == 201, created.text
        article_id = created.json()["id"]

    async with admin_factory() as s:
        row = (
            await s.execute(
                select(AuditLog).where(
                    AuditLog.entity == "kb_article", AuditLog.entity_id == article_id
                )
            )
        ).scalar_one()
        assert row.action == "create"
        assert row.tenant_id == tid
        assert row.actor_login == "william"
        assert row.actor_type == "agent"
        assert "Como solicitar acesso à VPN" in row.description
        # nunca grava o corpo do artigo, só título/metadados
        assert "passo a passo" not in row.description
        assert "body_markdown" not in row.metadata_json


@pytest.mark.asyncio
async def test_create_kb_article_succeeds_even_if_audit_write_fails(
    engine, app_session_factory, monkeypatch
):
    st = _settings(monkeypatch)
    admin_factory = _wire(monkeypatch, engine, app_session_factory)
    tid = await _seed_tenant(engine, subdomain="aurora-audit-fail")

    def _boom(*args, **kwargs):
        raise RuntimeError("audit_log indisponível (simulado)")

    # Simula falha real na gravação da auditoria (ex.: DB fora do ar) sem
    # tocar no restante de `AdminSessionLocal`, usado por `_resolve_tenant`.
    monkeypatch.setattr(audit_service, "AuditLog", _boom)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        base = f"/v1/admin/tenants/{tid}/kb/articles"

        created = await c.post(
            base,
            json={
                "title": "Artigo sobrevive à falha de auditoria",
                "body_markdown": "conteúdo",
                "category": "rede",
                "tags": [],
                "visibility": "public",
                "status": "draft",
            },
        )
        # operação principal não é derrubada pela falha best-effort da auditoria
        assert created.status_code == 201, created.text
        article_id = created.json()["id"]

    async with admin_factory() as s:
        # confirma que a falha foi real: nenhuma linha foi gravada para esta criação
        row = (
            await s.execute(
                select(AuditLog).where(
                    AuditLog.entity == "kb_article", AuditLog.entity_id == article_id
                )
            )
        ).scalar_one_or_none()
        assert row is None
