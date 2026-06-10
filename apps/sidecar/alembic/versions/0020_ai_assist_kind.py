"""ai_generation_log.kind aceita 'assist' (Spec #1S)

Relaxa o CHECK de kind para incluir 'assist' (assistente de escrita do portal,
cliente-facing). A coluna agent_login guarda o customer_login nas linhas de
assist (reuso; tabela operacional sem RLS, mesmo padrão de 0016).

Revision ID: 0020_ai_assist_kind
Revises: 0019_agent_inventory
Create Date: 2026-06-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020_ai_assist_kind"
down_revision: str | None = "0019_agent_inventory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Nome REAL no Postgres: a convenção de nomes do metadata prefixou o nome do
# CheckConstraint (`ck_ai_generation_log_kind`, declarado em 0016) com o nome
# da tabela → `ck_ai_generation_log_` + `ck_ai_generation_log_kind`.
_CONSTRAINT = "ck_ai_generation_log_ck_ai_generation_log_kind"


def upgrade() -> None:
    # asyncpg não aceita múltiplos comandos num prepared statement: 1 op.execute por DDL.
    op.execute(f"ALTER TABLE gerti.ai_generation_log DROP CONSTRAINT {_CONSTRAINT}")
    op.execute(
        f"ALTER TABLE gerti.ai_generation_log ADD CONSTRAINT {_CONSTRAINT} "
        "CHECK (kind IN ('summary','reply','assist'))"
    )


def downgrade() -> None:
    # Estreitar o CHECK exige que nenhuma linha use o valor removido. ai_generation_log
    # é um log de auditoria operacional (não-tenant); na reversão removemos as linhas
    # kind='assist' antes de recriar o constraint estrito (senão o ADD falha).
    op.execute(f"ALTER TABLE gerti.ai_generation_log DROP CONSTRAINT {_CONSTRAINT}")
    op.execute("DELETE FROM gerti.ai_generation_log WHERE kind = 'assist'")
    op.execute(
        f"ALTER TABLE gerti.ai_generation_log ADD CONSTRAINT {_CONSTRAINT} "
        "CHECK (kind IN ('summary','reply'))"
    )
