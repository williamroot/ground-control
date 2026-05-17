"""contract_cycle + consumption_event (append-only) + glosa (+RLS)

Revision ID: 0007_cycle_consumption
Revises: 0006_catalog_scope
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_cycle_consumption"
down_revision: str | None = "0006_catalog_scope"
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
    # 1. contract_cycle (referenced by consumption_event.closing_cycle_id).
    op.create_table(
        "contract_cycle",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.contract.id"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            postgresql.ENUM(name="cycle_kind", schema="gerti", create_type=False),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="cycle_status", schema="gerti", create_type=False),
            nullable=False,
            server_default=sa.text("'open'::gerti.cycle_status"),  # H1
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("totals", postgresql.JSONB()),
        sa.UniqueConstraint(
            "contract_id",
            "kind",
            "period_start",
            name="uq_contract_cycle_contract_id_kind_period_start",
        ),
        schema="gerti",
    )
    op.create_index(
        "ix_contract_cycle_contract_id_status",
        "contract_cycle",
        ["contract_id", "status"],
        schema="gerti",
    )  # Spec #0 §4
    op.execute(
        "CREATE INDEX ix_contract_cycle_period_end_open "
        "ON gerti.contract_cycle (period_end) WHERE status = 'open'"
    )
    # H7 — no tenant_id: isolate via the owning contract (USING + WITH CHECK).
    op.execute("ALTER TABLE gerti.contract_cycle ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.contract_cycle FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY contract_cycle_tenant_isolation ON gerti.contract_cycle "
        "USING (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid)) "
        "WITH CHECK (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid))"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.contract_cycle TO gerti_app")

    # 2. consumption_event — append-only ledger (H4 Identity → has a sequence).
    op.create_table(
        "consumption_event",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.contract.id"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column("source_ref", sa.String(), nullable=False),
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.service_catalog_item.id"),
        ),
        sa.Column("billable_minutes", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("billable_amount_brl", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("unit_price_at_event", sa.Numeric(14, 2)),
        # H8 — settled-by pointer, UUID, NO ForeignKey (avoids circular FK).
        sa.Column("glosa_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "closing_cycle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.contract_cycle.id"),
        ),
        sa.Column("recorded_by", sa.String(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("webhook_event_id", postgresql.UUID(as_uuid=True)),
        schema="gerti",
    )
    # Idempotency: same webhook delivery never recorded twice.
    op.execute(
        "CREATE UNIQUE INDEX consumption_event_idempotency "
        "ON gerti.consumption_event (webhook_event_id) "
        "WHERE webhook_event_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_consumption_event_contract_id_occurred_at "
        "ON gerti.consumption_event (contract_id, occurred_at DESC)"
    )
    op.create_index(
        "ix_consumption_event_closing_cycle_id",
        "consumption_event",
        ["closing_cycle_id"],
        schema="gerti",
    )
    op.create_index(
        "ix_consumption_event_source_ref",
        "consumption_event",
        ["source_ref"],
        schema="gerti",
    )
    # H2 — append-only: DELETE always forbidden; UPDATE forbidden UNLESS the
    # only changed columns are closing_cycle_id and/or glosa_id (settlement
    # bookkeeping by CycleService.close() / glosa flow). The immutable ROW(...)
    # list is EXACTLY the model columns minus closing_cycle_id and glosa_id.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION gerti.consumption_event_append_only()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'consumption_event é append-only (DELETE proibido)';
            END IF;
            -- UPDATE: only closing_cycle_id and/or glosa_id may change.
            IF ROW(NEW.id, NEW.contract_id, NEW.occurred_at, NEW.source_kind,
                    NEW.source_ref, NEW.service_id, NEW.billable_minutes,
                    NEW.billable_amount_brl, NEW.unit_price_at_event,
                    NEW.recorded_by, NEW.recorded_at, NEW.webhook_event_id)
               IS DISTINCT FROM
               ROW(OLD.id, OLD.contract_id, OLD.occurred_at, OLD.source_kind,
                    OLD.source_ref, OLD.service_id, OLD.billable_minutes,
                    OLD.billable_amount_brl, OLD.unit_price_at_event,
                    OLD.recorded_by, OLD.recorded_at, OLD.webhook_event_id)
            THEN
                RAISE EXCEPTION
                    'consumption_event é append-only: só closing_cycle_id/glosa_id podem mudar';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_consumption_event_append_only "
        "BEFORE UPDATE OR DELETE ON gerti.consumption_event "
        "FOR EACH ROW EXECUTE FUNCTION gerti.consumption_event_append_only()"
    )
    # H7 — no tenant_id: isolate via the owning contract (USING + WITH CHECK).
    op.execute("ALTER TABLE gerti.consumption_event ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.consumption_event FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY consumption_event_tenant_isolation ON gerti.consumption_event "
        "USING (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid)) "
        "WITH CHECK (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid))"
    )
    # Append-only: SELECT, INSERT, UPDATE only (no DELETE). UPDATE is needed
    # for the settlement columns; the trigger still forbids ledger mutation
    # and DELETE — RLS + trigger + grant are now consistent.
    op.execute("GRANT SELECT, INSERT, UPDATE ON gerti.consumption_event TO gerti_app")

    # 3. glosa — billing write-off request against a consumption_event.
    op.create_table(
        "glosa",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "consumption_event_id",
            sa.BigInteger(),
            sa.ForeignKey("gerti.consumption_event.id"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="glosa_status", schema="gerti", create_type=False),
            nullable=False,
            server_default=sa.text("'pending'::gerti.glosa_status"),  # H1
        ),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("requested_by", sa.String(), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("reviewed_by", sa.String()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewer_note", sa.String()),
        schema="gerti",
    )
    op.create_index(
        "ix_glosa_consumption_event_id",
        "glosa",
        ["consumption_event_id"],
        schema="gerti",
    )
    op.create_index("ix_glosa_status", "glosa", ["status"], schema="gerti")
    # H7 — no tenant_id: isolate via consumption_event → contract.
    op.execute("ALTER TABLE gerti.glosa ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.glosa FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY glosa_tenant_isolation ON gerti.glosa "
        "USING (consumption_event_id IN (SELECT ce.id FROM gerti.consumption_event ce "
        "JOIN gerti.contract c ON c.id = ce.contract_id WHERE c.tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid)) "
        "WITH CHECK (consumption_event_id IN (SELECT ce.id FROM gerti.consumption_event ce "
        "JOIN gerti.contract c ON c.id = ce.contract_id WHERE c.tenant_id = "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid))"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.glosa TO gerti_app")

    # B2 — consumption_event.id is sa.Identity(always=False) → Postgres creates
    # an implicit sequence (gerti.consumption_event_id_seq). gerti_app needs
    # USAGE (nextval) + SELECT (currval) on it, or every INSERT as
    # gerti_sidecar fails with "permission denied for sequence". The 0002
    # baseline's GRANT ON ALL SEQUENCES is NOT retroactive — this identity
    # sequence is created NOW (0007), so it must be granted explicitly.
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA gerti TO gerti_app")


def downgrade() -> None:
    # FK-safe reverse order: glosa → consumption_event → contract_cycle.
    op.execute("REVOKE ALL ON gerti.glosa FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS glosa_tenant_isolation ON gerti.glosa")
    op.drop_index("ix_glosa_status", table_name="glosa", schema="gerti")
    op.drop_index("ix_glosa_consumption_event_id", table_name="glosa", schema="gerti")
    op.drop_table("glosa", schema="gerti")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_consumption_event_append_only " "ON gerti.consumption_event"
    )
    op.execute("DROP FUNCTION IF EXISTS gerti.consumption_event_append_only()")
    op.execute("REVOKE ALL ON gerti.consumption_event FROM gerti_app")
    op.execute(
        "DROP POLICY IF EXISTS consumption_event_tenant_isolation " "ON gerti.consumption_event"
    )
    op.drop_index(
        "ix_consumption_event_source_ref",
        table_name="consumption_event",
        schema="gerti",
    )
    op.drop_index(
        "ix_consumption_event_closing_cycle_id",
        table_name="consumption_event",
        schema="gerti",
    )
    op.execute("DROP INDEX IF EXISTS gerti.ix_consumption_event_contract_id_occurred_at")
    op.execute("DROP INDEX IF EXISTS gerti.consumption_event_idempotency")
    op.drop_table("consumption_event", schema="gerti")

    op.execute("REVOKE ALL ON gerti.contract_cycle FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS contract_cycle_tenant_isolation ON gerti.contract_cycle")
    op.execute("DROP INDEX IF EXISTS gerti.ix_contract_cycle_period_end_open")
    op.drop_index(
        "ix_contract_cycle_contract_id_status",
        table_name="contract_cycle",
        schema="gerti",
    )
    op.drop_table("contract_cycle", schema="gerti")
