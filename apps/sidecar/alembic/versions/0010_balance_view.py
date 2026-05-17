"""Balance materialized view gerti.contract_balance_current (admin/reporting-scope)

Revision ID: 0010_balance_view
Revises: 0009_rls_znuny_instance
Create Date: 2026-05-17

S3 — the matview uses the SAME single glosa rule as ConsumptionService.balance()
and CycleService.close(): a consumption is removed from the balance ONLY when it
is written off by an `approved` glosa. `glosa_id IS NULL`, a `pending` glosa, OR
a `rejected` glosa ALL still COUNT. The FILTER predicate keeps an event in the
sum/count iff it is NOT written off — `glosa_id IS NULL` OR there is NO
`approved` glosa for it.

RLS BYPASS — KNOWN & ACCEPTED: Postgres materialized views are NOT
row-level-security filtered (RLS applies to base tables, not the matview's
stored rows). gerti.contract_balance_current therefore exposes ALL tenants'
balances to anyone with SELECT. Mitigation baked into the design:
(1) it is reporting/refresh-job only, never queried on a tenant-facing path;
(2) tenant-facing balance is served exclusively by ConsumptionService.balance()
which runs under the tenant GUC against RLS'd base tables;
(3) the matview is documented here and in INTEGRATION.md as admin-scope.
Do NOT add a tenant-scoped query against this matview anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_balance_view"
down_revision: str | None = "0009_rls_znuny_instance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE MATERIALIZED VIEW gerti.contract_balance_current AS
        SELECT
          c.id AS contract_id,
          c.type,
          CASE c.type
            WHEN 'credit_brl' THEN
              c.initial_amount_brl - COALESCE(SUM(ce.billable_amount_brl) FILTER (
                WHERE ce.glosa_id IS NULL OR NOT EXISTS (
                  SELECT 1 FROM gerti.glosa g
                  WHERE g.id = ce.glosa_id AND g.status = 'approved')), 0)
            WHEN 'hour_bank' THEN
              c.initial_hours - COALESCE(SUM(ce.billable_minutes) FILTER (
                WHERE ce.glosa_id IS NULL OR NOT EXISTS (
                  SELECT 1 FROM gerti.glosa g
                  WHERE g.id = ce.glosa_id AND g.status = 'approved')), 0) / 60.0
            WHEN 'service_count' THEN
              c.initial_service_count - COALESCE(COUNT(ce.*) FILTER (
                WHERE ce.source_kind = 'service_item' AND (
                  ce.glosa_id IS NULL OR NOT EXISTS (
                    SELECT 1 FROM gerti.glosa g
                    WHERE g.id = ce.glosa_id AND g.status = 'approved'))), 0)
            ELSE NULL
          END AS remaining
        FROM gerti.contract c
        LEFT JOIN gerti.consumption_event ce ON ce.contract_id = c.id
        GROUP BY c.id;
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_contract_balance_current_contract_id "
        "ON gerti.contract_balance_current (contract_id)"
    )
    op.execute("GRANT SELECT ON gerti.contract_balance_current TO gerti_app")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS gerti.ix_contract_balance_current_contract_id")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS gerti.contract_balance_current")
