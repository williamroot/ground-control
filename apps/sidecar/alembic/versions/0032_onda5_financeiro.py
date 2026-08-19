"""Onda 5 — financeiro e fluxo: as duas decisões abertas viram COLUNA (R3/R6/R7/R15)

Revision ID: 0032_onda5_financeiro
Revises: 0031_recurring_task
Create Date: 2026-08-19

Esta migration existe, sobretudo, para materializar **duas decisões que
estavam abertas** no plano de campanha e que o William autorizou fechar por
suposição. Nenhuma das duas virou constante no código: ambas são **coluna por
contrato**, porque contratos de MSP diferem entre si — uma chave global daria
a resposta errada para metade dos clientes.

## D-Q — mensalidade de contrato de valor fixo é por ciclo ou por mês?

`contract.initial_amount_brl` é semanticamente sobrecarregado: em `credit_brl`
é saldo consumível, em `closed_value` vira valor de mensalidade. A correção da
Onda 0 emite **1 mensalidade por ciclo**, o que significa que um contrato com
fechamento trimestral fatura 1x o valor contratado, e não 3x.

**Assumido:** o valor contratado é **mensal** (`billing_amount_period =
'month'`), e um ciclo trimestral cobra 3x. É a forma mais comum em MSP e a que
o próprio nome "mensalidade" sugere. Quem tiver contrato cotado por fechamento
muda a coluna para `'cycle'` — por contrato, sem migração nem deploy.

## D-R — saldo acumulado entre ciclos tem teto e validade?

Hoje o acúmulo é ilimitado e sem expiração, porque foi assim que saiu ao
corrigir a cobrança indevida da Onda 0. Contratos reais costumam ter cap ("no
máximo uma franquia") ou prazo ("saldo de janeiro expira em 90 dias").

**Assumido:** mantém ilimitado **por padrão** (colunas nulas = sem limite), e
quem precisar preenche `carry_over_cap_*` e/ou `carry_over_expires_days`. O
padrão preserva o comportamento atual; a capacidade passa a existir.

## O resto

- `approval_required` + papel `approver` + `ticket_approval` (R7)
- `tenant_billing_config` (R6) — SMS/e-mail/financeiro por cliente
- tipo de contrato `free` (D-D, "livre"): cobrança sem contrato preservando a
  invariante do #1C, em vez de afrouxar o vínculo obrigatório
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0032_onda5_financeiro"
down_revision: str | None = "0031_recurring_task"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enable_tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE gerti.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE gerti.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON gerti.{table} "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.{table} TO gerti_app")


def upgrade() -> None:
    # ── D-D: o tipo "livre" ────────────────────────────────────────────────
    # Cobrança sem contrato, preservando a invariante do #1C (todo consumo
    # pertence a um contrato) em vez de afrouxá-la. O cliente avulso ganha um
    # contrato do tipo `free`: acumula consumo faturável, sem saldo e sem
    # alerta de saldo baixo.
    op.execute("ALTER TYPE gerti.contract_type ADD VALUE IF NOT EXISTS 'free'")

    # ── D-Q e D-R: coluna por contrato, nunca constante ────────────────────
    op.add_column(
        "contract",
        sa.Column(
            "billing_amount_period",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'month'"),
        ),
        schema="gerti",
    )
    op.create_check_constraint(
        "ck_contract_billing_amount_period",
        "contract",
        "billing_amount_period IN ('month','cycle')",
        schema="gerti",
    )
    for col in ("carry_over_cap_minutes", "carry_over_cap_amount_brl"):
        op.add_column("contract", sa.Column(col, sa.Numeric(14, 2)), schema="gerti")
    op.add_column("contract", sa.Column("carry_over_expires_days", sa.Integer()), schema="gerti")

    # ── T-R3.3: o chamado de origem do consumo ─────────────────────────────
    # `service_count` cobra por ATENDIMENTO, e atendimento é o chamado — não o
    # lançamento de hora (um chamado com três apontamentos é um atendimento,
    # não três). `source_ref` não serve para contar: vira `znuny:article:<id>`
    # sempre que há artigo, e o id do chamado se perde. Coluna nova, nullable:
    # evento antigo e evento que não vem de chamado ficam NULL.
    op.add_column(
        "consumption_event", sa.Column("znuny_ticket_id", sa.BigInteger()), schema="gerti"
    )
    op.create_index(
        "ix_consumption_event_ticket",
        "consumption_event",
        ["contract_id", "znuny_ticket_id"],
        schema="gerti",
        postgresql_where=sa.text("znuny_ticket_id IS NOT NULL"),
    )

    # ── T-R15.5: boleto e nota fiscal emitidos pelo Asaas ──────────────────
    # A fatura interna (`gerti.invoice`) passa a guardar o vínculo com a
    # cobrança e com a nota no Asaas. Colunas na própria fatura, não tabela
    # nova: a relação é 1-para-1 e o operador pergunta "cadê o boleto DESTA
    # fatura", nunca "liste as cobranças".
    for col in (
        "asaas_payment_id",
        "asaas_charge_status",
        "asaas_bank_slip_url",
        "asaas_invoice_url",
        "nfe_id",
        "nfe_status",
        "nfe_pdf_url",
    ):
        op.add_column("invoice", sa.Column(col, sa.Text()), schema="gerti")
    # Único: uma cobrança do Asaas não pode apontar para duas faturas. É por
    # este id que o webhook encontra a fatura para dar baixa.
    op.create_index(
        "ux_invoice_asaas_payment",
        "invoice",
        ["asaas_payment_id"],
        unique=True,
        schema="gerti",
        postgresql_where=sa.text("asaas_payment_id IS NOT NULL"),
    )

    # ── R7: aprovação de chamados ──────────────────────────────────────────
    op.add_column(
        "tenant",
        sa.Column(
            "approval_required", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        schema="gerti",
    )
    op.execute("ALTER TYPE gerti.portal_role ADD VALUE IF NOT EXISTS 'approver'")

    op.create_table(
        "ticket_approval",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("znuny_ticket_id", sa.Integer(), nullable=False),
        # `status` como CHECK de texto, não enum nativo novo — padrão adotado
        # na 0021 e mantido: enum no Postgres é caro de evoluir.
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column("approver_login", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected')", name="ck_ticket_approval_status"
        ),
        # Uma decisão por chamado. É o que faz a segunda chamada virar 409 em
        # vez de sobrescrever silenciosamente a primeira.
        sa.UniqueConstraint(
            "tenant_id", "znuny_ticket_id", name="uq_ticket_approval_tenant_ticket"
        ),
        schema="gerti",
    )
    _enable_tenant_rls("ticket_approval")

    # ── R6: configuração de faturamento por cliente ────────────────────────
    op.create_table(
        "tenant_billing_config",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # Defaults SEGUROS: tudo desligado. Ligar aviso automático para um
        # cliente é decisão dele, não estado herdado de um default nosso —
        # ainda mais no SMS, que tem custo por mensagem.
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sms_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("billing_email", sa.Text()),
        sa.Column("billing_phone", sa.Text()),
        sa.Column("billing_day", sa.SmallInteger()),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_by", sa.Text()),
        sa.CheckConstraint(
            "billing_day IS NULL OR (billing_day BETWEEN 1 AND 28)",
            name="ck_tenant_billing_config_day",
        ),
        schema="gerti",
    )
    _enable_tenant_rls("tenant_billing_config")


def downgrade() -> None:
    for table in ("tenant_billing_config", "ticket_approval"):
        op.execute(f"REVOKE ALL ON gerti.{table} FROM gerti_app")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON gerti.{table}")
        op.execute(f"ALTER TABLE gerti.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE gerti.{table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table, schema="gerti")
    op.drop_column("tenant", "approval_required", schema="gerti")
    op.drop_index("ux_invoice_asaas_payment", "invoice", schema="gerti")
    for col in (
        "nfe_pdf_url",
        "nfe_status",
        "nfe_id",
        "asaas_invoice_url",
        "asaas_bank_slip_url",
        "asaas_charge_status",
        "asaas_payment_id",
    ):
        op.drop_column("invoice", col, schema="gerti")
    op.drop_index("ix_consumption_event_ticket", "consumption_event", schema="gerti")
    op.drop_column("consumption_event", "znuny_ticket_id", schema="gerti")
    for col in (
        "carry_over_expires_days",
        "carry_over_cap_amount_brl",
        "carry_over_cap_minutes",
        "billing_amount_period",
    ):
        op.drop_column("contract", col, schema="gerti")
    # Valor de ENUM não é removível no Postgres sem recriar o tipo — os valores
    # `free` e `approver` PERMANECEM. Documentado de propósito: recriar um enum
    # em uso exigiria reescrever todas as colunas que o referenciam, o que num
    # downgrade de emergência é pior do que o valor órfão.
