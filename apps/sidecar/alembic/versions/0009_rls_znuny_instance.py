"""Backfill RLS ENABLE+FORCE on gerti.znuny_instance (S1 gap @ head 0008)

Revision ID: 0009_rls_znuny_instance
Revises: 0008_policy_ticketlink
Create Date: 2026-05-17

gerti.znuny_instance was created in 0001 and got DML granted to gerti_app in
0002, but never had RLS enabled. An unprivileged gerti_sidecar session could
therefore read/write EVERY tenant's instance rows unscoped — a real isolation
hole the S1 invariant test (test_every_gerti_table_has_rls_enabled_and_forced)
exposed at full-suite scope. This migration closes it.

znuny_instance has no tenant_id; a tenant reaches its instance via
gerti.tenant.znuny_instance_id. The policy scopes by the current tenant's
instance id (USING + WITH CHECK):

  - Fail-closed: unset / pooled-reset GUC → '' → NULLIF(...,'') → NULL → the
    `WHERE id = NULL::uuid` tenant subquery returns no rows → 0 znuny_instance
    rows visible/writable. No 22P02.
  - Admin onboarding (provisioning instances + tenants) runs as gerti_admin,
    which is BYPASSRLS, so this policy never blocks setup.
  - The `gerti.tenant` subquery works because gerti.tenant's own RLS
    (0002/0003) restricts the session to exactly its own tenant row
    (id = GUC), yielding precisely that tenant's znuny_instance_id.

gerti_app already holds the DML grant from 0002 — no re-grant / revoke here.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_rls_znuny_instance"
down_revision: str | None = "0008_policy_ticketlink"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE gerti.znuny_instance ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.znuny_instance FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY znuny_instance_tenant_isolation ON gerti.znuny_instance "
        "USING (id IN (SELECT znuny_instance_id FROM gerti.tenant "
        "WHERE id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)) "
        "WITH CHECK (id IN (SELECT znuny_instance_id FROM gerti.tenant "
        "WHERE id = NULLIF(current_setting('app.current_tenant', true), '')::uuid))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS znuny_instance_tenant_isolation ON gerti.znuny_instance")
    op.execute("ALTER TABLE gerti.znuny_instance NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.znuny_instance DISABLE ROW LEVEL SECURITY")
