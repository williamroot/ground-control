"""notification + user_preference (+RLS) — Spec #3 V3

Cria as tabelas gerti.notification e gerti.user_preference, ambas
tenant-scoped (FORCE RLS + policy direta por tenant_id). String +
CheckConstraint em vez de enum nativo (H1, evita CREATE TYPE). GRANT ao
role app real (gerti_app), igual à 0017/0021.

`notification`: mensagens dirigidas a um `recipient_login` dentro do
tenant — a policy RLS só isola por tenant; o escopo por destinatário é
responsabilidade da camada de serviço/router (ver domain/notification_service.py).

`user_preference`: 1 linha por (tenant_id, user_login), criada sob
demanda (get_or_create) por domain/preference_service.py.

Revision ID: 0023_notifications_prefs
Revises: 0022_kb_catalog
Create Date: 2026-07-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0023_notifications_prefs"
down_revision: str | None = "0022_kb_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOTIFICATION_KINDS = (
    "ticket_update",
    "ticket_reply",
    "sla_warning",
    "sla_breach",
    "contract_alert",
    "invoice_issued",
    "system",
)


def _enable_tenant_rls(table: str, tenant_col: str = "tenant_id") -> None:
    """RLS template idêntico ao da 0007/0017: ENABLE + FORCE + policy fail-closed."""
    op.execute(f"ALTER TABLE gerti.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE gerti.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON gerti.{table} "
        f"USING ({tenant_col} = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        f"WITH CHECK ({tenant_col} = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.{table} TO gerti_app")


def upgrade() -> None:
    # 1. notification
    op.create_table(
        "notification",
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
        sa.Column("recipient_login", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=True),
        sa.Column("link_path", sa.String(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "kind IN (" + ",".join(f"'{k}'" for k in _NOTIFICATION_KINDS) + ")",
            name="ck_notification_kind",
        ),
        schema="gerti",
    )
    op.execute(
        "CREATE INDEX ix_notification_tenant_recipient_created "
        "ON gerti.notification (tenant_id, recipient_login, created_at DESC)"
    )
    _enable_tenant_rls("notification")

    # 2. user_preference
    op.create_table(
        "user_preference",
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
        sa.Column("user_login", sa.String(), nullable=False),
        sa.Column("theme", sa.String(), nullable=False, server_default="system"),
        sa.Column(
            "email_notifications", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("sla_alerts", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("ticket_updates", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("contract_alerts", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("invoice_alerts", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("weekly_report", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
        sa.UniqueConstraint(
            "tenant_id", "user_login", name="uq_user_preference_tenant_id_user_login"
        ),
        sa.CheckConstraint("theme IN ('light','dark','system')", name="ck_user_preference_theme"),
        schema="gerti",
    )
    _enable_tenant_rls("user_preference")


def downgrade() -> None:
    op.execute("REVOKE ALL ON gerti.user_preference FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS user_preference_tenant_isolation ON gerti.user_preference")
    op.drop_table("user_preference", schema="gerti")

    op.execute("REVOKE ALL ON gerti.notification FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS notification_tenant_isolation ON gerti.notification")
    op.execute("DROP INDEX IF EXISTS gerti.ix_notification_tenant_recipient_created")
    op.drop_table("notification", schema="gerti")
