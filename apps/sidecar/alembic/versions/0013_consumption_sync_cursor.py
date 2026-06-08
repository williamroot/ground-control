"""consumption_sync_cursor — watermark do pull de time_accounting (Spec #1B)

Revision ID: 0013_consumption_sync_cursor
Revises: 0012_portal_user_role
Create Date: 2026-06-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_consumption_sync_cursor"
down_revision: str | None = "0012_portal_user_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consumption_sync_cursor",
        sa.Column(
            "znuny_instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.znuny_instance.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "last_time_accounting_id",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="gerti",
    )
    # Operacional, não-tenant: NÃO habilita RLS. Só o caminho admin
    # (gerti_admin_user, BYPASSRLS, dono do DDL) lê/escreve. gerti_app não
    # precisa de grant (o worker usa o engine admin para o cursor).


def downgrade() -> None:
    op.drop_table("consumption_sync_cursor", schema="gerti")
