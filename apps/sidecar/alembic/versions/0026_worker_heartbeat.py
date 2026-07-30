"""worker_heartbeat — prova de vida do worker de consumo, separada do cursor de
sincronização (Spec #3 — painel de saúde não pode confundir "ocioso" com "travado")

Revision ID: 0026_worker_heartbeat
Revises: 0025_audit_log_revoke_app
Create Date: 2026-07-30

`consumption_sync_cursor.updated_at` só avança quando o worker reconcilia
alguma coisa: em produção, um worker vivo e ocioso (sem lançamentos novos no
Znuny) fica com `updated_at` velho — indistinguível, pela sonda de saúde
antiga, de um worker travado. `worker_heartbeat` resolve isso: o worker grava
uma linha a CADA tick, com trabalho ou sem, sucesso ou falha.

`worker_heartbeat` é OPERACIONAL cross-tenant: SEM RLS, SEM GRANT a
`gerti_app` — só `AdminSessionLocal` (BYPASSRLS) lê/escreve (molde:
0013_consumption_sync_cursor + REVOKE explícito de 0025_audit_log_revoke_app,
porque os default privileges do schema `gerti` concedem sozinhos a `gerti_app`
se não revogarmos).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_worker_heartbeat"
down_revision: str | None = "0025_audit_log_revoke_app"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeat",
        sa.Column("worker", sa.Text(), primary_key=True),
        sa.Column("last_tick_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("ticks", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text()),
        schema="gerti",
    )
    # Operacional, não-tenant: NÃO habilita RLS. Default privileges do schema
    # `gerti` concedem SELECT/INSERT/UPDATE/DELETE a `gerti_app` sozinhos — "não
    # conceder" não basta, é preciso REVOKE explícito (já nos mordeu em audit_log).
    op.execute("REVOKE ALL ON gerti.worker_heartbeat FROM gerti_app")


def downgrade() -> None:
    op.drop_table("worker_heartbeat", schema="gerti")
