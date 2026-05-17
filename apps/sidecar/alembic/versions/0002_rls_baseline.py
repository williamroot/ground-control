"""rls baseline: ativa RLS em tenant e dá GRANT a gerti_app.

Revision ID: 0002_rls_baseline
Revises: 0001_initial
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_rls_baseline"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Grants para o app role consumir as tabelas
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.tenant TO gerti_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.znuny_instance TO gerti_app")
    op.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA gerti TO gerti_app")

    # RLS na tabela tenant (o próprio tenant só vê a si mesmo)
    op.execute("ALTER TABLE gerti.tenant ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_self_isolation ON gerti.tenant
          USING (
            current_setting('app.current_tenant', true) = ''
            OR id = current_setting('app.current_tenant', true)::uuid
          )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_self_isolation ON gerti.tenant")
    op.execute("ALTER TABLE gerti.tenant DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON gerti.tenant FROM gerti_app")
    op.execute("REVOKE ALL ON gerti.znuny_instance FROM gerti_app")
