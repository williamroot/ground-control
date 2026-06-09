"""csat_response — avaliação CSAT 1-5 do cliente por ticket (Spec #1M)

Tenant-scoped: FORCE ROW LEVEL SECURITY + policy por tenant_id + GRANT a
gerti_app (mesmo padrão das outras tabelas de negócio, ver 0007). UNIQUE
(tenant_id, znuny_ticket_id): 1 resposta por ticket.

Revision ID: 0015_csat
Revises: 0014_agent_timer
Create Date: 2026-06-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015_csat"
down_revision: str | None = "0014_agent_timer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "csat_response",
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
        sa.Column("znuny_ticket_id", sa.Integer(), nullable=False),
        sa.Column("customer_login", sa.String(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "znuny_ticket_id", name="ux_csat_ticket"),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ck_csat_response_score"),
        schema="gerti",
    )
    # Tenant-scoped: ENABLE + FORCE (até o dono obedece) + policy keyed no GUC.
    op.execute("ALTER TABLE gerti.csat_response ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.csat_response FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY csat_response_tenant_isolation ON gerti.csat_response "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute("GRANT SELECT, INSERT ON gerti.csat_response TO gerti_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON gerti.csat_response FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS csat_response_tenant_isolation ON gerti.csat_response")
    op.execute("ALTER TABLE gerti.csat_response NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.csat_response DISABLE ROW LEVEL SECURITY")
    op.drop_table("csat_response", schema="gerti")
