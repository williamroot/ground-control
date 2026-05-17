"""service_catalog_item + shared_credit_pool + contract scope tables (+RLS)

Revision ID: 0006_catalog_scope
Revises: 0005_contract_core
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_catalog_scope"
down_revision: str | None = "0005_contract_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enable_tenant_rls(table: str, tenant_col: str = "tenant_id") -> None:
    """Reusable RLS template for per-tenant contract tables.

    - ENABLE + FORCE so even the table owner obeys it.
    - Policy strictly keyed on the GUC cast to uuid (NO empty-GUC escape):
      unset GUC → NULL; pooled-conn reset GUC → '' (NOT NULL). NULLIF(...,'')
      collapses BOTH to NULL → comparison NULL → 0 rows (fail-closed, no
      22P02). Contract data must never leak with an unset/reset tenant.
    - gerti_app gets table + sequence DML grants (it never owns objects).
    """
    op.execute(f"ALTER TABLE gerti.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE gerti.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON gerti.{table} "
        f"USING ({tenant_col} = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        f"WITH CHECK ({tenant_col} = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.{table} TO gerti_app")


def _disable_tenant_rls(table: str) -> None:
    op.execute(f"REVOKE ALL ON gerti.{table} FROM gerti_app")
    op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON gerti.{table}")
    op.execute(f"ALTER TABLE gerti.{table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE gerti.{table} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    # 1. shared_credit_pool FIRST (referenced by the deferred FK below).
    op.create_table(
        "shared_credit_pool",
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
        sa.Column("total_amount_brl", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "cycle_kind",
            postgresql.ENUM(name="cycle_kind", schema="gerti", create_type=False),
            nullable=False,
        ),
        sa.Column("cycle_period_months", sa.Integer(), nullable=False),
        sa.Column("current_cycle_start", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="gerti",
    )
    # 2. H3 — add the deferred FK from contract.shared_pool_id.
    op.create_foreign_key(
        "fk_contract_shared_pool_id_shared_credit_pool",
        "contract",
        "shared_credit_pool",
        ["shared_pool_id"],
        ["id"],
        source_schema="gerti",
        referent_schema="gerti",
    )
    op.create_index(
        "ix_shared_credit_pool_tenant_id",
        "shared_credit_pool",
        ["tenant_id"],
        schema="gerti",
    )  # Spec #0 §4
    _enable_tenant_rls("shared_credit_pool")

    # 3. service_catalog_item, then scope tables.
    op.create_table(
        "service_catalog_item",
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
        ),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String()),
        sa.Column("category", sa.String()),
        sa.Column("default_queue_name", sa.String(), nullable=False),
        sa.Column("default_priority", sa.SmallInteger(), nullable=False, server_default="3"),
        sa.Column("default_sla_minutes", sa.Integer()),
        sa.Column(
            "form_schema",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("unit_price_brl", sa.Numeric(14, 2)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="gerti",
    )
    # S2 — Spec §4: unique on (COALESCE(tenant_id, zero-uuid), code) so a tenant
    # cannot collide with a global row's code and globals are unique too.
    op.execute(
        "CREATE UNIQUE INDEX uq_service_catalog_item_scope_code "
        "ON gerti.service_catalog_item "
        "(COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), code)"
    )
    op.create_index(
        "ix_service_catalog_item_tenant_active",
        "service_catalog_item",
        ["tenant_id", "active"],
        schema="gerti",
    )
    # B1 — split per-command RLS: global (tenant_id IS NULL) rows are
    # SELECT-only to tenants; writes are strictly the caller's own tenant_id.
    op.execute("ALTER TABLE gerti.service_catalog_item ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.service_catalog_item FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY service_catalog_item_tenant_select "
        "ON gerti.service_catalog_item FOR SELECT "
        "USING (tenant_id IS NULL "
        "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute(
        "CREATE POLICY service_catalog_item_tenant_insert "
        "ON gerti.service_catalog_item FOR INSERT "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute(
        "CREATE POLICY service_catalog_item_tenant_update "
        "ON gerti.service_catalog_item FOR UPDATE "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute(
        "CREATE POLICY service_catalog_item_tenant_delete "
        "ON gerti.service_catalog_item FOR DELETE "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE " "ON gerti.service_catalog_item TO gerti_app")

    op.create_table(
        "contract_scope_service",
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.contract.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.service_catalog_item.id"),
            primary_key=True,
        ),
        sa.Column("unit_price_override", sa.Numeric(14, 2)),
        schema="gerti",
    )
    op.create_table(
        "contract_scope_ci",
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.contract.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("znuny_ci_id", sa.Integer(), primary_key=True),
        sa.Column("covered_from", sa.Date(), primary_key=True),
        sa.Column("covered_until", sa.Date()),
        schema="gerti",
    )
    # H7 — scope tables have no tenant_id: isolate via their contract,
    # both USING and WITH CHECK identical (mirrors 0005 contract_billing_party).
    op.execute("ALTER TABLE gerti.contract_scope_service ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.contract_scope_service FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY contract_scope_service_tenant_isolation "
        "ON gerti.contract_scope_service "
        "USING (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid)) "
        "WITH CHECK (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid))"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE " "ON gerti.contract_scope_service TO gerti_app"
    )
    op.execute("ALTER TABLE gerti.contract_scope_ci ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.contract_scope_ci FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY contract_scope_ci_tenant_isolation "
        "ON gerti.contract_scope_ci "
        "USING (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid)) "
        "WITH CHECK (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid))"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE " "ON gerti.contract_scope_ci TO gerti_app")

    # B2 (uniformity): last statement of upgrade(). PKs here are UUID so no
    # sequence exists yet, but the idempotent grant keeps the chain uniform
    # with 0007 (GRANT ON ALL SEQUENCES is NOT retroactive).
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA gerti TO gerti_app")


def downgrade() -> None:
    # FK-safe reverse order: scope tables → service_catalog_item → FK → pool.
    op.execute("REVOKE ALL ON gerti.contract_scope_ci FROM gerti_app")
    op.execute(
        "DROP POLICY IF EXISTS contract_scope_ci_tenant_isolation " "ON gerti.contract_scope_ci"
    )
    op.drop_table("contract_scope_ci", schema="gerti")
    op.execute("REVOKE ALL ON gerti.contract_scope_service FROM gerti_app")
    op.execute(
        "DROP POLICY IF EXISTS contract_scope_service_tenant_isolation "
        "ON gerti.contract_scope_service"
    )
    op.drop_table("contract_scope_service", schema="gerti")

    op.execute(
        "DROP POLICY IF EXISTS service_catalog_item_tenant_select " "ON gerti.service_catalog_item"
    )
    op.execute(
        "DROP POLICY IF EXISTS service_catalog_item_tenant_insert " "ON gerti.service_catalog_item"
    )
    op.execute(
        "DROP POLICY IF EXISTS service_catalog_item_tenant_update " "ON gerti.service_catalog_item"
    )
    op.execute(
        "DROP POLICY IF EXISTS service_catalog_item_tenant_delete " "ON gerti.service_catalog_item"
    )
    op.execute("REVOKE ALL ON gerti.service_catalog_item FROM gerti_app")
    op.drop_index(
        "ix_service_catalog_item_tenant_active",
        table_name="service_catalog_item",
        schema="gerti",
    )
    op.execute("DROP INDEX IF EXISTS gerti.uq_service_catalog_item_scope_code")
    op.drop_table("service_catalog_item", schema="gerti")

    op.drop_constraint(
        "fk_contract_shared_pool_id_shared_credit_pool",
        "contract",
        schema="gerti",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_shared_credit_pool_tenant_id",
        table_name="shared_credit_pool",
        schema="gerti",
    )
    _disable_tenant_rls("shared_credit_pool")
    op.drop_table("shared_credit_pool", schema="gerti")
