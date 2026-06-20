"""Contratação self-service + Asaas (Spec #2).

Tabelas não-tenant (catálogo/config/operacionais) — o checkout é público e roda
antes de o tenant existir. Acessadas via AdminSessionLocal (BYPASSRLS). Strings
+ CheckConstraint (DB) com StrEnum no código (ver models/enums.py).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class PaymentProviderAccount(Base):
    __tablename__ = "payment_provider_account"
    __table_args__ = (
        CheckConstraint("owner_kind IN ('gerti','msp')", name="ck_provider_account_owner_kind"),
        CheckConstraint("mode IN ('sandbox','production')", name="ck_provider_account_mode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    owner_kind: Mapped[str] = mapped_column(String, nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id")
    )
    provider: Mapped[str] = mapped_column(String, nullable=False, server_default="asaas")
    mode: Mapped[str] = mapped_column(String, nullable=False)
    api_key_ref: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    webhook_token: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Plan(Base):
    __tablename__ = "plan"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_plan_slug"),
        CheckConstraint("audience IN ('end_client','msp')", name="ck_plan_audience"),
        CheckConstraint("billing_mode IN ('subscription','one_off')", name="ck_plan_billing_mode"),
        CheckConstraint("price_cents >= 0", name="ck_plan_price_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    slug: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    audience: Mapped[str] = mapped_column(String, nullable=False)
    contract_type: Mapped[str] = mapped_column(String, nullable=False)
    billing_mode: Mapped[str] = mapped_column(String, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    cycle: Mapped[str | None] = mapped_column(String)
    initial_amount_brl: Mapped[float | None] = mapped_column(Numeric(14, 2))
    initial_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    initial_service_count: Mapped[int | None] = mapped_column(Integer)
    unit_price_cents: Mapped[int | None] = mapped_column(Integer)
    billing_period_months: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    closing_period_months: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    provider_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.payment_provider_account.id")
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CheckoutSession(Base):
    __tablename__ = "checkout_session"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started','awaiting_payment','paid',"
            "'provisioned','failed','expired','canceled')",
            name="ck_checkout_status",
        ),
        CheckConstraint(
            "billing_type IN ('PIX','BOLETO','CREDIT_CARD')", name="ck_checkout_billing_type"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.plan.id"), nullable=False
    )
    provider_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.payment_provider_account.id")
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="started")
    target_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id")
    )
    applicant: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    billing_type: Mapped[str] = mapped_column(String, nullable=False)
    asaas_customer_id: Mapped[str | None] = mapped_column(String)
    asaas_subscription_id: Mapped[str | None] = mapped_column(String)
    asaas_payment_id: Mapped[str | None] = mapped_column(String)
    guest_token: Mapped[str] = mapped_column(String, nullable=False)
    provisioned_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id")
    )
    error: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Payment(Base):
    __tablename__ = "payment"
    __table_args__ = (
        UniqueConstraint("asaas_payment_id", name="uq_payment_asaas_payment_id"),
        CheckConstraint(
            "billing_type IN ('PIX','BOLETO','CREDIT_CARD')", name="ck_payment_billing_type"
        ),
        CheckConstraint(
            "status IN ('pending','confirmed','received','overdue','refunded','failed','canceled')",
            name="ck_payment_status",
        ),
        CheckConstraint("value_cents >= 0", name="ck_payment_value_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    checkout_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.checkout_session.id")
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id")
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract.id")
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.invoice.id")
    )
    provider: Mapped[str] = mapped_column(String, nullable=False, server_default="asaas")
    asaas_payment_id: Mapped[str | None] = mapped_column(String)
    asaas_subscription_id: Mapped[str | None] = mapped_column(String)
    billing_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="pending")
    value_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[dt.date | None] = mapped_column(Date)
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    external_reference: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AsaasWebhookEvent(Base):
    __tablename__ = "asaas_webhook_event"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_asaas_webhook_event_event_id"),
        CheckConstraint(
            "status IN ('received','processed','failed')", name="ck_asaas_webhook_event_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    event_id: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="received")
    error: Mapped[str | None] = mapped_column(String)
    received_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
