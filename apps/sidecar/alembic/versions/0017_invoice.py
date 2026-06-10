"""invoice + invoice_line (fatura interna não-fiscal, +RLS) — Spec #1P

Cria o enum gerti.invoice_status e as tabelas invoice/invoice_line, ambas
tenant-scoped (FORCE RLS + policy direta por tenant_id). invoice_line tem
tenant_id denormalizado p/ policy simples + índice. GRANT ao role app real
(gerti_app, igual à 0007).

Revision ID: 0017_invoice
Revises: 0016_ai_generation_log
Create Date: 2026-06-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017_invoice"
down_revision: str | None = "0016_ai_generation_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enable_tenant_rls(table: str, tenant_col: str = "tenant_id") -> None:
    """RLS template idêntico ao da 0007: ENABLE + FORCE + policy fail-closed."""
    op.execute(f"ALTER TABLE gerti.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE gerti.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON gerti.{table} "
        f"USING ({tenant_col} = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        f"WITH CHECK ({tenant_col} = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.{table} TO gerti_app")


def upgrade() -> None:
    op.execute(
        "CREATE TYPE gerti.invoice_status AS ENUM " "('draft', 'open', 'paid', 'overdue', 'void')"
    )

    # 1. invoice
    op.create_table(
        "invoice",
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
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.contract.id"),
            nullable=False,
        ),
        sa.Column(
            "cycle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.contract_cycle.id"),
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="invoice_status", schema="gerti", create_type=False),
            nullable=False,
            server_default=sa.text("'open'::gerti.invoice_status"),  # H1
        ),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="BRL"),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pdf_bytes", sa.LargeBinary()),
        sa.Column("pdf_generated_at", sa.DateTime(timezone=True)),
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
        sa.UniqueConstraint("tenant_id", "number", name="uq_invoice_tenant_id_number"),
        # 1 fatura por ciclo (idempotência). NULLs não colidem no Postgres.
        sa.UniqueConstraint("cycle_id", name="uq_invoice_cycle_id"),
        sa.CheckConstraint("total_cents >= 0", name="ck_invoice_total_cents_non_negative"),
        sa.CheckConstraint("subtotal_cents >= 0", name="ck_invoice_subtotal_cents_non_negative"),
        schema="gerti",
    )
    op.create_index(
        "ix_invoice_tenant_id_status",
        "invoice",
        ["tenant_id", "status"],
        schema="gerti",
    )
    op.create_index(
        "ix_invoice_contract_id",
        "invoice",
        ["contract_id"],
        schema="gerti",
    )
    op.execute(
        "CREATE INDEX ix_invoice_due_at_open ON gerti.invoice (due_at) WHERE status = 'open'"
    )
    _enable_tenant_rls("invoice")

    # 2. invoice_line (tenant_id denormalizado → policy direta + índice)
    op.create_table(
        "invoice_line",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.invoice.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id"),
            nullable=False,
        ),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(), nullable=False, server_default=""),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        schema="gerti",
    )
    op.create_index(
        "ix_invoice_line_invoice_id",
        "invoice_line",
        ["invoice_id"],
        schema="gerti",
    )
    op.create_index(
        "ix_invoice_line_tenant_id",
        "invoice_line",
        ["tenant_id"],
        schema="gerti",
    )
    _enable_tenant_rls("invoice_line")


def downgrade() -> None:
    op.execute("REVOKE ALL ON gerti.invoice_line FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS invoice_line_tenant_isolation ON gerti.invoice_line")
    op.drop_index("ix_invoice_line_tenant_id", table_name="invoice_line", schema="gerti")
    op.drop_index("ix_invoice_line_invoice_id", table_name="invoice_line", schema="gerti")
    op.drop_table("invoice_line", schema="gerti")

    op.execute("REVOKE ALL ON gerti.invoice FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS invoice_tenant_isolation ON gerti.invoice")
    op.execute("DROP INDEX IF EXISTS gerti.ix_invoice_due_at_open")
    op.drop_index("ix_invoice_contract_id", table_name="invoice", schema="gerti")
    op.drop_index("ix_invoice_tenant_id_status", table_name="invoice", schema="gerti")
    op.drop_table("invoice", schema="gerti")

    op.execute("DROP TYPE IF EXISTS gerti.invoice_status")
