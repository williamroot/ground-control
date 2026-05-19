"""tenant_branding (1:1 with tenant) with the per-tenant RLS template

Revision ID: 0011_tenant_branding
Revises: 0010_balance_view
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011_tenant_branding"
down_revision: str | None = "0010_balance_view"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enable_tenant_rls(table: str, tenant_col: str = "tenant_id") -> None:
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
        "tenant_branding",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("logo_url", sa.String()),
        sa.Column(
            "primary_color", sa.String(), nullable=False, server_default=sa.text("'#2563EB'")
        ),
        sa.Column("accent_color", sa.String(), nullable=False, server_default=sa.text("'#1E40AF'")),
        sa.Column("default_theme", sa.String(), nullable=False, server_default=sa.text("'light'")),
        sa.Column("support_email", sa.String()),
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
        sa.CheckConstraint("default_theme IN ('light','dark')", name="ck_tenant_branding_theme"),
        schema="gerti",
    )
    _enable_tenant_rls("tenant_branding")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA gerti TO gerti_app")


def downgrade() -> None:
    _disable_tenant_rls("tenant_branding")
    op.drop_table("tenant_branding", schema="gerti")
