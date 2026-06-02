"""portal_user_role (papel admin/helpdesk por usuário) + enum gerti.portal_role

Spec #1H. FORCE RLS por tenant (template canônico, igual 0011). Unicidade real
por índice funcional (tenant_id, lower(customer_login)) — case-insensitive,
casando com a resolução de papel no login.

Revision ID: 0012_portal_user_role
Revises: 0011_tenant_branding
Create Date: 2026-06-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012_portal_user_role"
down_revision: str | None = "0011_tenant_branding"
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
    op.execute("CREATE TYPE gerti.portal_role AS ENUM ('admin', 'helpdesk')")
    op.create_table(
        "portal_user_role",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("customer_login", sa.String(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(
                "admin", "helpdesk", name="portal_role", schema="gerti", create_type=False
            ),
            nullable=False,
        ),
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
        schema="gerti",
    )
    # Unicidade case-insensitive por tenant — casa com lower(customer_login)
    # usado na resolução do papel no login.
    op.execute(
        "CREATE UNIQUE INDEX uq_portal_user_role_tenant_login "
        "ON gerti.portal_user_role (tenant_id, lower(customer_login))"
    )
    _enable_tenant_rls("portal_user_role")


def downgrade() -> None:
    _disable_tenant_rls("portal_user_role")
    op.drop_table("portal_user_role", schema="gerti")  # remove índices junto
    op.execute("DROP TYPE IF EXISTS gerti.portal_role")
