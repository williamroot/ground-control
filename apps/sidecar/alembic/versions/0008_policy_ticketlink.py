"""contract_adjustment_rule + contract_renewal_policy + ticket_contract_link (+RLS)

Revision ID: 0008_policy_ticketlink
Revises: 0007_cycle_consumption
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_policy_ticketlink"
down_revision: str | None = "0007_cycle_consumption"
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
    # 1. contract_adjustment_rule — contract_id PK only (no tenant_id).
    op.create_table(
        "contract_adjustment_rule",
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.contract.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("index_code", sa.String(), nullable=False),
        sa.Column("cadence_months", sa.Integer(), nullable=False),
        sa.Column("next_run_on", sa.Date(), nullable=False),
        sa.Column("cap_percent", sa.Numeric(5, 2)),
        sa.Column("last_applied_on", sa.Date()),
        sa.Column("last_applied_percent", sa.Numeric(6, 3)),
        schema="gerti",
    )
    # H7 — no tenant_id: isolate via the owning contract (USING + WITH CHECK).
    op.execute("ALTER TABLE gerti.contract_adjustment_rule ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.contract_adjustment_rule FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY contract_adjustment_rule_tenant_isolation "
        "ON gerti.contract_adjustment_rule "
        "USING (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid)) "
        "WITH CHECK (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid))"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE " "ON gerti.contract_adjustment_rule TO gerti_app"
    )

    # 2. contract_renewal_policy — contract_id PK only (no tenant_id).
    op.create_table(
        "contract_renewal_policy",
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.contract.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "auto_renew",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "notice_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column("next_review_on", sa.Date(), nullable=False),
        sa.Column("renewal_term_months", sa.Integer()),
        schema="gerti",
    )
    # H7 — no tenant_id: isolate via the owning contract (USING + WITH CHECK).
    op.execute("ALTER TABLE gerti.contract_renewal_policy ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.contract_renewal_policy FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY contract_renewal_policy_tenant_isolation "
        "ON gerti.contract_renewal_policy "
        "USING (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid)) "
        "WITH CHECK (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid))"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE " "ON gerti.contract_renewal_policy TO gerti_app"
    )

    # 3. ticket_contract_link — has its own tenant_id → standard template.
    op.create_table(
        "ticket_contract_link",
        sa.Column("znuny_ticket_id", sa.Integer(), primary_key=True),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.contract.id"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id"),
            nullable=False,
        ),
        sa.Column(
            "billing_status",
            postgresql.ENUM(name="billing_status", schema="gerti", create_type=False),
            nullable=False,
            server_default=sa.text("'pending'::gerti.billing_status"),  # H1
        ),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("linked_by_rule", sa.String(), nullable=False),
        schema="gerti",
    )
    op.create_index(
        "ix_ticket_contract_link_contract_id",
        "ticket_contract_link",
        ["contract_id"],
        schema="gerti",
    )  # Spec #0 §4
    op.create_index(
        "ix_ticket_contract_link_tenant_id_billing_status",
        "ticket_contract_link",
        ["tenant_id", "billing_status"],
        schema="gerti",
    )  # Spec #0 §4
    _enable_tenant_rls("ticket_contract_link")

    # B2 — uniformity: these 3 tables have UUID/Integer PKs with no implicit
    # sequence, but the "always grant" rule prevents a future Identity column
    # regressing (GRANT ON ALL SEQUENCES is NOT retroactive). Harmless here.
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA gerti TO gerti_app")


def downgrade() -> None:
    # FK-safe reverse order: ticket_contract_link → renewal_policy →
    # adjustment_rule (policy/renewal tables have no inbound FKs).
    _disable_tenant_rls("ticket_contract_link")
    op.drop_index(
        "ix_ticket_contract_link_tenant_id_billing_status",
        table_name="ticket_contract_link",
        schema="gerti",
    )
    op.drop_index(
        "ix_ticket_contract_link_contract_id",
        table_name="ticket_contract_link",
        schema="gerti",
    )
    op.drop_table("ticket_contract_link", schema="gerti")

    op.execute("REVOKE ALL ON gerti.contract_renewal_policy FROM gerti_app")
    op.execute(
        "DROP POLICY IF EXISTS contract_renewal_policy_tenant_isolation "
        "ON gerti.contract_renewal_policy"
    )
    op.drop_table("contract_renewal_policy", schema="gerti")

    op.execute("REVOKE ALL ON gerti.contract_adjustment_rule FROM gerti_app")
    op.execute(
        "DROP POLICY IF EXISTS contract_adjustment_rule_tenant_isolation "
        "ON gerti.contract_adjustment_rule"
    )
    op.drop_table("contract_adjustment_rule", schema="gerti")
