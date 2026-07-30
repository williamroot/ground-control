"""audit_log — trilha de auditoria operacional (Spec #3 V5) + branding 'system' (V4)

Revision ID: 0024_audit_log
Revises: 0023_notifications_prefs
Create Date: 2026-07-30

`audit_log` é OPERACIONAL cross-tenant: SEM RLS, SEM GRANT a `gerti_app` — só
`AdminSessionLocal` (BYPASSRLS) lê/escreve (molde: 0013_consumption_sync_cursor).

Também alarga o CHECK `ck_tenant_branding_theme` de `('light','dark')` para
incluir `'system'` — requisito do editor de identidade visual (V4, mesmo
agente/migration; `tenant_branding` é reusada, não recriada).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0024_audit_log"
down_revision: str | None = "0023_notifications_prefs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_login", sa.String()),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id", ondelete="SET NULL"),
        ),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String()),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("ip", sa.String()),
        sa.Column("user_agent", sa.String()),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "actor_type IN ('agent','customer','system')", name="ck_audit_log_actor_type"
        ),
        sa.CheckConstraint(
            "action IN ('create','update','delete','login','export')",
            name="ck_audit_log_action",
        ),
        schema="gerti",
    )
    op.create_index("ix_audit_log_at", "audit_log", ["at"], schema="gerti")
    op.create_index("ix_audit_log_tenant_id_at", "audit_log", ["tenant_id", "at"], schema="gerti")
    # Operacional, não-tenant: NÃO habilita RLS, NÃO faz GRANT a gerti_app — só
    # o caminho admin (AdminSessionLocal, BYPASSRLS) lê/escreve.

    # V4: o editor de identidade visual precisa do tema 'system' além de light|dark.
    #
    # Pegadinha real: a `NAMING_CONVENTION` do projeto é aplicada pelo Alembic às
    # operações, então o CHECK declarado na 0011 como `ck_tenant_branding_theme`
    # foi materializado no banco com o prefixo DUPLICADO —
    # `ck_tenant_branding_ck_tenant_branding_theme`. Derrubamos os DOIS nomes
    # (`IF EXISTS`, idempotente) e recriamos com SQL explícito, que não passa pela
    # convenção. Usar `op.create_check_constraint` aqui reintroduziria a duplicação.
    op.execute(
        "ALTER TABLE gerti.tenant_branding "
        "DROP CONSTRAINT IF EXISTS ck_tenant_branding_ck_tenant_branding_theme"
    )
    op.execute(
        "ALTER TABLE gerti.tenant_branding DROP CONSTRAINT IF EXISTS ck_tenant_branding_theme"
    )
    op.execute(
        "ALTER TABLE gerti.tenant_branding ADD CONSTRAINT ck_tenant_branding_theme "
        "CHECK (default_theme IN ('light','dark','system'))"
    )


def downgrade() -> None:
    # Volta ao CHECK estreito da 0011. Linhas com 'system' precisam ser
    # normalizadas antes, senão o ADD CONSTRAINT falha — por isso o UPDATE.
    op.execute(
        "ALTER TABLE gerti.tenant_branding DROP CONSTRAINT IF EXISTS ck_tenant_branding_theme"
    )
    op.execute(
        "ALTER TABLE gerti.tenant_branding "
        "DROP CONSTRAINT IF EXISTS ck_tenant_branding_ck_tenant_branding_theme"
    )
    op.execute(
        "UPDATE gerti.tenant_branding SET default_theme = 'light' WHERE default_theme = 'system'"
    )
    op.execute(
        "ALTER TABLE gerti.tenant_branding ADD CONSTRAINT ck_tenant_branding_theme "
        "CHECK (default_theme IN ('light','dark'))"
    )
    op.drop_index("ix_audit_log_tenant_id_at", table_name="audit_log", schema="gerti")
    op.drop_index("ix_audit_log_at", table_name="audit_log", schema="gerti")
    op.drop_table("audit_log", schema="gerti")
