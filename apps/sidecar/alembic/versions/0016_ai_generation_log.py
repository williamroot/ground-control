"""ai_generation_log — auditoria/custo de geração de IA (Spec #1N)

Tabela OPERACIONAL cross-tenant, SEM RLS (mesmo padrão de agent_timer/0014):
dono = gerti_admin_user, lida/gravada via AdminSessionLocal (BYPASSRLS). Não
recebe policy nem GRANT a gerti_app (o caminho de cliente nunca a toca).

Revision ID: 0016_ai_generation_log
Revises: 0015_csat
Create Date: 2026-06-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016_ai_generation_log"
down_revision: str | None = "0015_csat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_generation_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("agent_login", sa.String(), nullable=False),
        sa.Column("znuny_ticket_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),  # summary | reply
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("kind IN ('summary','reply')", name="ck_ai_generation_log_kind"),
        schema="gerti",
    )
    # Operacional/não-tenant: SEM RLS. Dono = gerti_admin_user (caminho admin).


def downgrade() -> None:
    op.drop_table("ai_generation_log", schema="gerti")
