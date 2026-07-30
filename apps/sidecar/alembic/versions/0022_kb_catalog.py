"""kb_article + catalog_item (+RLS) — Spec #3 V1/V2 (agente B1)

Cria `gerti.kb_article` (Base de Conhecimento) e `gerti.catalog_item`
(Catálogo de Serviços do portal), ambas tenant-scoped (FORCE RLS + policy
direta por tenant_id, GRANT ao gerti_app). String + CheckConstraint em vez de
enum nativo (evita CREATE TYPE / footgun de cast — H1).

Nota: o contrato da Spec #3 reserva o nome `service_catalog_item` para a
tabela do V2, mas esse nome já existe (`gerti.service_catalog_item`, Spec #0
§4 — billing/consumo, referenciada por FK em contract_scope/consumption).
Por isso a tabela nasce como `gerti.catalog_item` — código existente vence.

Revision ID: 0022_kb_catalog
Revises: 0021_contratacao_asaas
Create Date: 2026-07-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0022_kb_catalog"
down_revision: str | None = "0021_contratacao_asaas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enable_tenant_rls(table: str, tenant_col: str = "tenant_id") -> None:
    """RLS template idêntico ao da 0007/0017: ENABLE + FORCE + policy fail-closed."""
    op.execute(f"ALTER TABLE gerti.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE gerti.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON gerti.{table} "
        f"USING ({tenant_col} = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        f"WITH CHECK ({tenant_col} = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.{table} TO gerti_app")


def upgrade() -> None:
    # 1. kb_article
    op.create_table(
        "kb_article",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("summary", sa.String()),
        sa.Column("body_markdown", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("author_login", sa.String()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_kb_article_tenant_id_slug"),
        sa.CheckConstraint("visibility IN ('public', 'internal')", name="ck_kb_article_visibility"),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')", name="ck_kb_article_status"
        ),
        schema="gerti",
    )
    op.create_index(
        "ix_kb_article_tenant_id_status",
        "kb_article",
        ["tenant_id", "status"],
        schema="gerti",
    )
    op.create_index(
        "ix_kb_article_tenant_id_category",
        "kb_article",
        ["tenant_id", "category"],
        schema="gerti",
    )
    _enable_tenant_rls("kb_article")

    # 2. catalog_item (nome real; ver nota de topo sobre a colisão com
    # gerti.service_catalog_item, já existente na Spec #0 §4)
    op.create_table(
        "catalog_item",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("description", sa.String()),
        sa.Column("sla_hours", sa.Integer()),
        sa.Column("icon", sa.String(), nullable=False, server_default="ticket"),
        sa.Column("znuny_queue", sa.String()),
        sa.Column("znuny_service", sa.String()),
        sa.Column("default_priority", sa.String()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "icon IN ('ticket', 'shield', 'user-plus', 'server', 'package', 'database', "
            "'box', 'printer', 'lock', 'wifi', 'mail', 'settings')",
            name="ck_catalog_item_icon",
        ),
        sa.CheckConstraint(
            "sla_hours IS NULL OR sla_hours BETWEEN 1 AND 720",
            name="ck_catalog_item_sla_hours",
        ),
        sa.CheckConstraint("sort_order BETWEEN 0 AND 999", name="ck_catalog_item_sort_order"),
        schema="gerti",
    )
    op.create_index(
        "ix_catalog_item_tenant_id_active",
        "catalog_item",
        ["tenant_id", "active"],
        schema="gerti",
    )
    op.create_index(
        "ix_catalog_item_tenant_id_category",
        "catalog_item",
        ["tenant_id", "category"],
        schema="gerti",
    )
    _enable_tenant_rls("catalog_item")


def downgrade() -> None:
    op.execute("REVOKE ALL ON gerti.catalog_item FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS catalog_item_tenant_isolation ON gerti.catalog_item")
    op.drop_index("ix_catalog_item_tenant_id_category", table_name="catalog_item", schema="gerti")
    op.drop_index("ix_catalog_item_tenant_id_active", table_name="catalog_item", schema="gerti")
    op.drop_table("catalog_item", schema="gerti")

    op.execute("REVOKE ALL ON gerti.kb_article FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS kb_article_tenant_isolation ON gerti.kb_article")
    op.drop_index("ix_kb_article_tenant_id_category", table_name="kb_article", schema="gerti")
    op.drop_index("ix_kb_article_tenant_id_status", table_name="kb_article", schema="gerti")
    op.drop_table("kb_article", schema="gerti")
