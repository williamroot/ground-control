"""agent_enroll_token + device_agent — auto-registro de equipamentos (Spec #1R-a)

Tenant-scoped: FORCE ROW LEVEL SECURITY + policy por tenant_id + GRANT a
gerti_app (mesmo padrão de 0007/0015/0018).
- agent_enroll_token: token de instalação por tenant; token_hash sha256 UNIQUE;
  travas expires_at/max_registrations/enabled; registration_count.
- device_agent: equipamento; UNIQUE(tenant_id, fingerprint) (dedupe); status
  pending|active|revoked (CHECK); agent_secret_hash sha256; specs JSONB.

Revision ID: 0019_agent_inventory
Revises: 0018_automation
Create Date: 2026-06-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019_agent_inventory"
down_revision: str | None = "0018_automation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _force_rls(table: str, policy: str, grants: str) -> None:
    op.execute(f"ALTER TABLE gerti.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE gerti.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {policy} ON gerti.{table} "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute(f"GRANT {grants} ON gerti.{table} TO gerti_app")


def upgrade() -> None:
    op.create_table(
        "agent_enroll_token",
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
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("max_registrations", sa.Integer()),
        sa.Column("registration_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("token_hash", name="ux_agent_enroll_token_hash"),
        schema="gerti",
    )

    op.create_table(
        "device_agent",
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
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("agent_secret_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("znuny_config_item_id", sa.Integer()),
        sa.Column("hostname", sa.String(), nullable=False),
        sa.Column("os", sa.String()),
        sa.Column(
            "specs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
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
        sa.UniqueConstraint("tenant_id", "fingerprint", name="ux_device_agent_tenant_fingerprint"),
        sa.CheckConstraint(
            "status IN ('pending','active','revoked')", name="ck_device_agent_status"
        ),
        schema="gerti",
    )

    _force_rls(
        "agent_enroll_token",
        "agent_enroll_token_tenant_isolation",
        "SELECT, INSERT, UPDATE, DELETE",
    )
    _force_rls(
        "device_agent",
        "device_agent_tenant_isolation",
        "SELECT, INSERT, UPDATE, DELETE",
    )


def downgrade() -> None:
    op.execute("REVOKE ALL ON gerti.device_agent FROM gerti_app")
    op.execute("DROP POLICY IF EXISTS device_agent_tenant_isolation ON gerti.device_agent")
    op.execute("ALTER TABLE gerti.device_agent NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.device_agent DISABLE ROW LEVEL SECURITY")
    op.drop_table("device_agent", schema="gerti")

    op.execute("REVOKE ALL ON gerti.agent_enroll_token FROM gerti_app")
    op.execute(
        "DROP POLICY IF EXISTS agent_enroll_token_tenant_isolation ON gerti.agent_enroll_token"
    )
    op.execute("ALTER TABLE gerti.agent_enroll_token NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gerti.agent_enroll_token DISABLE ROW LEVEL SECURITY")
    op.drop_table("agent_enroll_token", schema="gerti")
