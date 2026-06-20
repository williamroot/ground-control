"""contratação self-service + integração Asaas (Spec #2 / contratação)

Tabelas NÃO-tenant (catálogo/config/operacionais), acessadas via AdminSessionLocal
(BYPASSRLS): o checkout é público e roda ANTES de o tenant existir (modelo
pré-cadastro → paga → webhook provisiona). Sem FORCE RLS no MVP; quando os
pagamentos forem expostos no portal por-tenant (fase 2), adiciona-se policy.
Strings + CheckConstraint (como tenant.status) em vez de enums nativos —
mais simples e sem os footguns de cast (H1). GRANT ao gerti_app por simetria.

Revision ID: 0021_contratacao_asaas
Revises: 0020_ai_assist_kind
Create Date: 2026-06-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0021_contratacao_asaas"
down_revision: str | None = "0020_ai_assist_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("payment", "checkout_session", "plan", "payment_provider_account", "asaas_webhook_event")


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        primary_key=True,
    )


def _ts(name: str, *, default_now: bool = True, nullable: bool = False) -> sa.Column:
    kw = {}
    if default_now:
        kw["server_default"] = sa.text("now()")
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, **kw)


def upgrade() -> None:
    # 1. payment_provider_account — conta Asaas (Gerti default e/ou por MSP).
    op.create_table(
        "payment_provider_account",
        _uuid_pk(),
        sa.Column("owner_kind", sa.String(), nullable=False),  # gerti | msp
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(), nullable=False, server_default="asaas"),
        sa.Column("mode", sa.String(), nullable=False),  # sandbox | production
        # Referência ao segredo (nome de env var / chave de cofre) — NUNCA a key crua.
        sa.Column("api_key_ref", sa.String(), nullable=False),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column("webhook_token", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _ts("created_at"),
        sa.CheckConstraint("owner_kind IN ('gerti','msp')", name="ck_provider_account_owner_kind"),
        sa.CheckConstraint("mode IN ('sandbox','production')", name="ck_provider_account_mode"),
        schema="gerti",
    )
    op.create_index(
        "ix_provider_account_owner_tenant",
        "payment_provider_account",
        ["owner_kind", "tenant_id"],
        schema="gerti",
    )

    # 2. plan — catálogo de planos vendáveis (público).
    op.create_table(
        "plan",
        _uuid_pk(),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("audience", sa.String(), nullable=False),  # end_client | msp
        sa.Column("contract_type", sa.String(), nullable=False),  # = gerti.contract_type
        sa.Column("billing_mode", sa.String(), nullable=False),  # subscription | one_off
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("cycle", sa.String(), nullable=True),  # MONTHLY/YEARLY... quando subscription
        sa.Column("initial_amount_brl", sa.Numeric(14, 2), nullable=True),
        sa.Column("initial_hours", sa.Numeric(10, 2), nullable=True),
        sa.Column("initial_service_count", sa.Integer(), nullable=True),
        sa.Column("unit_price_cents", sa.Integer(), nullable=True),
        sa.Column("billing_period_months", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("closing_period_months", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "provider_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.payment_provider_account.id"),
            nullable=True,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _ts("created_at"),
        sa.UniqueConstraint("slug", name="uq_plan_slug"),
        sa.CheckConstraint("audience IN ('end_client','msp')", name="ck_plan_audience"),
        sa.CheckConstraint(
            "billing_mode IN ('subscription','one_off')", name="ck_plan_billing_mode"
        ),
        sa.CheckConstraint("price_cents >= 0", name="ck_plan_price_non_negative"),
        schema="gerti",
    )

    # 3. checkout_session — captura o prospecto ANTES do pagamento (tenant pode não existir).
    op.create_table(
        "checkout_session",
        _uuid_pk(),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.plan.id"),
            nullable=False,
        ),
        sa.Column(
            "provider_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.payment_provider_account.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="started"),
        sa.Column(
            "target_tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id"),
            nullable=True,
        ),
        sa.Column(
            "applicant", postgresql.JSONB(), nullable=False
        ),  # empresa+admin+branding (SEM senha)
        sa.Column("billing_type", sa.String(), nullable=False),  # PIX | BOLETO | CREDIT_CARD
        sa.Column("asaas_customer_id", sa.String(), nullable=True),
        sa.Column("asaas_subscription_id", sa.String(), nullable=True),
        sa.Column("asaas_payment_id", sa.String(), nullable=True),
        sa.Column("guest_token", sa.String(), nullable=False),
        sa.Column(
            "provisioned_tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id"),
            nullable=True,
        ),
        sa.Column("error", sa.String(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        _ts("expires_at", default_now=False, nullable=True),
        sa.CheckConstraint(
            "status IN ('started','awaiting_payment','paid',"
            "'provisioned','failed','expired','canceled')",
            name="ck_checkout_status",
        ),
        sa.CheckConstraint(
            "billing_type IN ('PIX','BOLETO','CREDIT_CARD')", name="ck_checkout_billing_type"
        ),
        schema="gerti",
    )
    op.create_index("ix_checkout_session_status", "checkout_session", ["status"], schema="gerti")
    op.create_index(
        "ix_checkout_session_asaas_payment",
        "checkout_session",
        ["asaas_payment_id"],
        schema="gerti",
    )

    # 4. payment — espelho local de cada cobrança Asaas (avulsa ou parcela de assinatura).
    op.create_table(
        "payment",
        _uuid_pk(),
        sa.Column(
            "checkout_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.checkout_session.id"),
            nullable=True,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.tenant.id"),
            nullable=True,
        ),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.contract.id"),
            nullable=True,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gerti.invoice.id"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(), nullable=False, server_default="asaas"),
        sa.Column("asaas_payment_id", sa.String(), nullable=True),
        sa.Column("asaas_subscription_id", sa.String(), nullable=True),
        sa.Column("billing_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("value_cents", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_reference", sa.String(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("asaas_payment_id", name="uq_payment_asaas_payment_id"),
        sa.CheckConstraint(
            "billing_type IN ('PIX','BOLETO','CREDIT_CARD')", name="ck_payment_billing_type"
        ),
        sa.CheckConstraint(
            "status IN ('pending','confirmed','received','overdue','refunded','failed','canceled')",
            name="ck_payment_status",
        ),
        sa.CheckConstraint("value_cents >= 0", name="ck_payment_value_non_negative"),
        schema="gerti",
    )
    op.create_index("ix_payment_tenant_id", "payment", ["tenant_id"], schema="gerti")
    op.create_index(
        "ix_payment_checkout_session_id", "payment", ["checkout_session_id"], schema="gerti"
    )

    # 5. asaas_webhook_event — idempotência (event_id único) + auditoria do payload bruto.
    op.create_table(
        "asaas_webhook_event",
        _uuid_pk(),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="received"),
        sa.Column("error", sa.String(), nullable=True),
        _ts("received_at"),
        _ts("processed_at", default_now=False, nullable=True),
        sa.UniqueConstraint("event_id", name="uq_asaas_webhook_event_event_id"),
        sa.CheckConstraint(
            "status IN ('received','processed','failed')", name="ck_asaas_webhook_event_status"
        ),
        schema="gerti",
    )

    for t in _TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON gerti.{t} TO gerti_app")


def downgrade() -> None:
    for t in _TABLES:
        op.execute(f"REVOKE ALL ON gerti.{t} FROM gerti_app")
    op.drop_table("asaas_webhook_event", schema="gerti")
    op.drop_table("payment", schema="gerti")
    op.drop_table("checkout_session", schema="gerti")
    op.drop_table("plan", schema="gerti")
    op.drop_table("payment_provider_account", schema="gerti")
