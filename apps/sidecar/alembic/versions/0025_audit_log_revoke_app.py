"""revoga gerti_app de gerti.audit_log (fecha brecha de default privileges) — Spec #3 V5

Revision ID: 0025_audit_log_revoke_app
Revises: 0024_audit_log
Create Date: 2026-07-30

A 0024 criou `audit_log` deliberadamente **sem** `GRANT` a `gerti_app` (é tabela
operacional cross-tenant, lida só por `AdminSessionLocal`/BYPASSRLS em
`/v1/admin/*`). Só que "não conceder" não é suficiente: o init do cluster
(`infra/compose/postgres/init/001_schemas_and_roles.sql`) tem
`ALTER DEFAULT PRIVILEGES ... GRANT ... TO gerti_app` no schema `gerti`, então a
tabela nasceu com SELECT/INSERT/UPDATE/DELETE para `gerti_app` mesmo assim —
verificado ao vivo em staging.

Isso importa porque `audit_log` **não tem RLS**: o papel de runtime
(`gerti_sidecar`, membro de `gerti_app`) conseguiria ler a trilha de **todos** os
tenants. Hoje nenhum caminho de cliente consulta essa tabela, então não há
vazamento real — mas a única barreira seria o código, e a intenção do desenho era
que fosse o banco. Este REVOKE restaura a intenção.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025_audit_log_revoke_app"
down_revision: str | None = "0024_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("REVOKE ALL ON gerti.audit_log FROM gerti_app")


def downgrade() -> None:
    # Espelho: devolve o que os default privileges do schema teriam concedido.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.audit_log TO gerti_app")
