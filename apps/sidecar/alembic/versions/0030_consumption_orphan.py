"""consumption_orphan — hora que o worker não conseguiu atribuir a contrato (T-R2.3)

Revision ID: 0030_consumption_orphan
Revises: 0029_tenant_queue
Create Date: 2026-08-15

O alerta mais caro do levantamento: o vínculo chamado↔contrato só nasce quando
o chamado entra pelo **portal**. `reconciliation_service` descarta lançamento de
chamado sem vínculo e **avança o cursor mesmo assim** — hora trabalhada em
chamado que entrou por e-mail sumiria sem erro e sem aviso. Ligar e-mail (R9,
Onda 2) antes de resolver isto faria a Gerti perder faturamento em silêncio.

Decisão D-E (fechada 15/08): **não mexer no avanço do cursor** — é código
financeiro vivo, e a alternativa (segurar o cursor) trava a reconciliação
inteira por causa de um lançamento órfão. Em vez disso, o descarte deixa de ser
silencioso: cada lançamento não atribuível vira uma linha aqui, reprocessável.

`reason` diz por que não deu:
  • `no_tenant`            — o CustomerID do chamado não casa com nenhum tenant
  • `no_active_contract`   — tenant existe, zero contrato ativo
  • `ambiguous_contract`   — tenant existe, ≥2 contratos ativos (precisa de humano)

Operacional cross-tenant, igual a `worker_heartbeat` (0026) e
`consumption_sync_cursor` (0013): **sem RLS** (o `tenant_id` é justamente o que
pode faltar) e **sem GRANT** a `gerti_app` — só `AdminSessionLocal` (BYPASSRLS)
lê/escreve. Os default privileges do schema `gerti` concedem sozinhos se não
revogarmos explicitamente; daí o REVOKE.

`znuny_time_accounting_id` é UNIQUE: o worker é idempotente por lançamento, e um
re-scan da mesma faixa não pode multiplicar a pendência.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0030_consumption_orphan"
down_revision: str | None = "0029_tenant_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consumption_orphan",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("znuny_time_accounting_id", sa.BigInteger(), nullable=False),
        sa.Column("znuny_ticket_id", sa.Integer(), nullable=False),
        sa.Column("znuny_customer_id", sa.Text()),
        # nullable: o caso `no_tenant` é exatamente "não sei de quem é".
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("time_unit", sa.Numeric(10, 2), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_contract_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "reason IN ('no_tenant','no_active_contract','ambiguous_contract')",
            name="ck_consumption_orphan_reason",
        ),
        sa.CheckConstraint("status IN ('pending','resolved')", name="ck_consumption_orphan_status"),
        sa.UniqueConstraint("znuny_time_accounting_id", name="uq_consumption_orphan_ta"),
        schema="gerti",
    )
    op.execute(
        "CREATE INDEX ix_consumption_orphan_pending ON gerti.consumption_orphan "
        "(created_at DESC) WHERE status = 'pending'"
    )
    op.execute("REVOKE ALL ON gerti.consumption_orphan FROM gerti_app")


def downgrade() -> None:
    op.drop_index("ix_consumption_orphan_pending", table_name="consumption_orphan", schema="gerti")
    op.drop_table("consumption_orphan", schema="gerti")
