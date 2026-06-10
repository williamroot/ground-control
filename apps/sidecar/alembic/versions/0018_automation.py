"""automation_rule + automation_run — motor de automação (Spec #1Q)

Tenant-scoped: FORCE ROW LEVEL SECURITY + policy por tenant_id + GRANT a
gerti_app (mesmo padrão das outras tabelas de negócio, ver 0007/0015).
- automation_rule: regra no-code (trigger + conditions JSONB + actions JSONB).
  CHECK em trigger_event = allowlist do domínio.
- automation_run: registro append-only de cada avaliação (FK rule_id → rule).

Revision ID: 0018_automation
Revises: 0017_invoice
Create Date: 2026-06-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018_automation"
down_revision: str | None = "0017_invoice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _force_rls(table: str, policy: str, grants: str) -> None:
    op.execute(f"ALTER TABLE gerti.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE gerti.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {policy} ON gerti.{table} "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute(f"GRANT {grants} ON gerti.{table} TO gerti_app")


def upgrade() -> None:
    op.create_table(
        "automation_rule",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("trigger_event", sa.String(), nullable=False),
        sa.Column(
            "conditions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "actions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
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
            "trigger_event IN ('ticket_create','article_create','state_update','escalation')",
            name="ck_automation_rule_trigger_event",
        ),
        schema="gerti",
    )

    op.create_table(
        "automation_run",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id"),
            nullable=False,
        ),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.automation_rule.id"),
            nullable=False,
        ),
        sa.Column("znuny_ticket_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("matched", sa.Boolean(), nullable=False),
        sa.Column("actions_result", postgresql.JSONB()),
        sa.Column("error", sa.String()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="gerti",
    )

    _force_rls(
        "automation_rule",
        "automation_rule_tenant_isolation",
        "SELECT, INSERT, UPDATE, DELETE",
    )
    _force_rls(
        "automation_run",
        "automation_run_tenant_isolation",
        "SELECT, INSERT",
    )


def downgrade() -> None:
    op.execute("REVOKE ALL ON gerti.automation_run FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS automation_run_tenant_isolation ON gerti.automation_run")
    op.execute("ALTER TABLE gerti.automation_run NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.automation_run DISABLE ROW LEVEL SECURITY")
    op.drop_table("automation_run", schema="gerti")

    op.execute("REVOKE ALL ON gerti.automation_rule FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS automation_rule_tenant_isolation ON gerti.automation_rule")
    op.execute("ALTER TABLE gerti.automation_rule NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.automation_rule DISABLE ROW LEVEL SECURITY")
    op.drop_table("automation_rule", schema="gerti")
