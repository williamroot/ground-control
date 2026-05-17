"""force RLS on gerti.tenant + drop empty-GUC escape for contract safety

Revision ID: 0003_force_rls_tenant
Revises: 0002_rls_baseline
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_force_rls_tenant"
down_revision: str | None = "0002_rls_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Owner must also obey RLS (defense-in-depth; gerti_admin still BYPASSRLS).
    op.execute("ALTER TABLE gerti.tenant FORCE ROW LEVEL SECURITY")
    # Replace the permissive self-isolation policy: NO empty-GUC escape.
    op.execute("DROP POLICY IF EXISTS tenant_self_isolation ON gerti.tenant")
    op.execute(
        """
        CREATE POLICY tenant_tenant_isolation ON gerti.tenant
            USING (id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_tenant_isolation ON gerti.tenant")
    op.execute(
        """
        CREATE POLICY tenant_self_isolation ON gerti.tenant
            USING (
                current_setting('app.current_tenant', true) = ''
                OR id = current_setting('app.current_tenant', true)::uuid
            )
        """
    )
    op.execute("ALTER TABLE gerti.tenant NO FORCE ROW LEVEL SECURITY")
