"""contract + contract_billing_party with the per-tenant RLS template

Revision ID: 0005_contract_core
Revises: 0004_contract_enums
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_contract_core"
down_revision: str | None = "0004_contract_enums"  # AUDITED REAL HEAD
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
    op.create_table(
        "contract",
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
        sa.Column("code", sa.String(), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(name="contract_type", schema="gerti", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="contract_status", schema="gerti", create_type=False),
            nullable=False,
            server_default=sa.text("'active'::gerti.contract_status"),
        ),  # H1
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("initial_amount_brl", sa.Numeric(14, 2)),
        sa.Column("initial_hours", sa.Numeric(10, 2)),
        sa.Column("initial_service_count", sa.Integer()),
        sa.Column("unit_price_brl", sa.Numeric(14, 2)),
        sa.Column("travel_franchise_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("billing_period_months", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("closing_period_months", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "billing_in_advance", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "accumulate_balance_between_cycles",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        # H3: column only — FK to gerti.shared_credit_pool is added in 0006
        # (Task 5), AFTER that table exists. Do NOT add sa.ForeignKey here.
        sa.Column("shared_pool_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_contract_tenant_id_code"),
        sa.CheckConstraint("ends_on > starts_on", name="ck_contract_dates"),
        sa.CheckConstraint(
            "closing_period_months % billing_period_months = 0 "
            "OR billing_period_months % closing_period_months = 0",
            name="ck_contract_cycle_multiple",
        ),
        schema="gerti",
    )
    op.create_index(
        "ix_contract_tenant_status", "contract", ["tenant_id", "status"], schema="gerti"
    )
    # Spec #0 §4 partial indexes (were missing from the draft plan):
    op.create_index(
        "ix_contract_ends_on_active",
        "contract",
        ["ends_on"],
        schema="gerti",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_contract_shared_pool_id",
        "contract",
        ["shared_pool_id"],
        schema="gerti",
        postgresql_where=sa.text("shared_pool_id IS NOT NULL"),
    )
    op.create_table(
        "contract_billing_party",
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.contract.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("legal_name", sa.String(), nullable=False),
        sa.Column("document", sa.String(), nullable=False),
        sa.Column("fiscal_address", postgresql.JSONB(), nullable=False),
        sa.Column("payment_method", sa.String()),
        schema="gerti",
    )
    _enable_tenant_rls("contract")
    # contract_billing_party has no tenant_id; isolate via its contract.
    op.execute("ALTER TABLE gerti.contract_billing_party ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.contract_billing_party FORCE ROW LEVEL SECURITY")
    # H7: child-table policy needs explicit WITH CHECK identical to USING,
    # else cross-tenant INSERT could slip through the USING fallback.
    op.execute(
        "CREATE POLICY contract_billing_party_tenant_isolation "
        "ON gerti.contract_billing_party "
        "USING (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid)) "
        "WITH CHECK (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid))"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.contract_billing_party " "TO gerti_app"
    )
    # B2 (uniformity): last statement of upgrade(). contract PKs are UUID so
    # no sequence exists yet, but emitting the idempotent grant here keeps the
    # rule "every contract-domain migration grants ALL SEQUENCES" so a future
    # Identity/serial column can never regress (GRANT ON ALL SEQUENCES is NOT
    # retroactive — see B2 in Task 6 for the binding case, consumption_event).
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA gerti TO gerti_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON gerti.contract_billing_party FROM gerti_app")
    op.execute(
        "DROP POLICY IF EXISTS contract_billing_party_tenant_isolation "
        "ON gerti.contract_billing_party"
    )
    op.drop_table("contract_billing_party", schema="gerti")
    _disable_tenant_rls("contract")
    # B2: no sequence REVOKE — contract uses UUID PKs (no sequence); the
    # uniformity grant below is harmless residual.
    op.drop_index("ix_contract_shared_pool_id", table_name="contract", schema="gerti")
    op.drop_index("ix_contract_ends_on_active", table_name="contract", schema="gerti")
    op.drop_index("ix_contract_tenant_status", table_name="contract", schema="gerti")
    op.drop_table("contract", schema="gerti")
