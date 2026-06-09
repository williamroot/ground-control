"""agent_timer — cronômetro por (agente, ticket) (Spec #1J)

Revision ID: 0014_agent_timer
Revises: 0013_consumption_sync_cursor
Create Date: 2026-06-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014_agent_timer"
down_revision: str | None = "0013_consumption_sync_cursor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_timer",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("agent_login", sa.String(), nullable=False),
        sa.Column("znuny_ticket_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),  # running|paused|stopped
        sa.Column("accumulated_seconds", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_started_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.String()),
        sa.Column("committed_time_unit", sa.Numeric(10, 2)),
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
            "status IN ('running','paused','stopped')", name="ck_agent_timer_status"
        ),
        schema="gerti",
    )
    # No máximo UM timer ativo (running/paused) por (agente, ticket).
    op.execute(
        "CREATE UNIQUE INDEX ux_agent_timer_active ON gerti.agent_timer "
        "(agent_login, znuny_ticket_id) WHERE status <> 'stopped'"
    )
    # Operacional/não-tenant: SEM RLS. Dono = gerti_admin_user (caminho admin).


def downgrade() -> None:
    op.drop_index("ux_agent_timer_active", table_name="agent_timer", schema="gerti")
    op.drop_table("agent_timer", schema="gerti")
