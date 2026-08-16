"""tenant: endereço e contato (T-R1.1, Onda 1 — R1 do vídeo do Kleber)

Revision ID: 0027_tenant_address_contact
Revises: 0026_worker_heartbeat
Create Date: 2026-08-15

O Kleber trata endereço e contato como dado cadastral básico (01:10), e hoje
eles não existem em lugar nenhum — nem em `gerti.tenant`, nem no
`customer_company` do Znuny (a op GI grava só ID + nome).

Decisão D-B (fechada 15/08): `gerti.tenant` é **dona** do endereço; o Znuny
recebe um espelho best-effort (mesmo padrão já usado no branding). Por isso as
colunas nascem aqui, e não como leitura via GI.

Todas nullable: tenant existente continua inserível e legível sem tocar em
nada. RLS/FORCE da tabela permanece exatamente como estava — `ALTER TABLE ADD
COLUMN` não mexe em policy.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_tenant_address_contact"
down_revision: str | None = "0026_worker_heartbeat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    "address_street",
    "address_number",
    "address_complement",
    "address_district",
    "address_city",
    "address_state",
    "address_zip",
    "contact_name",
    "contact_email",
    "contact_phone",
)


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column("tenant", sa.Column(name, sa.Text(), nullable=True), schema="gerti")


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("tenant", name, schema="gerti")
