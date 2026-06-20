"""Enum types shared by the contract domain (mirror gerti.* Postgres enums)."""

from __future__ import annotations

from enum import StrEnum


class ContractType(StrEnum):
    closed_value = "closed_value"
    credit_brl = "credit_brl"
    credit_shared = "credit_shared"
    hour_bank = "hour_bank"
    saas_product = "saas_product"
    service_count = "service_count"


class ContractStatus(StrEnum):
    draft = "draft"
    active = "active"
    suspended = "suspended"
    expired = "expired"
    terminated = "terminated"


class CycleKind(StrEnum):
    billing = "billing"
    closing = "closing"


class CycleStatus(StrEnum):
    open = "open"
    closed = "closed"
    invoiced = "invoiced"


class GlosaStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class BillingStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    billed = "billed"
    disputed = "disputed"


class InvoiceStatus(StrEnum):
    """Status de uma fatura interna (Spec #1P). `paid`/`void` são terminais."""

    draft = "draft"
    open = "open"
    paid = "paid"
    overdue = "overdue"
    void = "void"


class PortalRole(StrEnum):
    """Papel do usuário no Portal do Cliente (Spec #1H)."""

    admin = "admin"  # vê contratos + valores financeiros
    helpdesk = "helpdesk"  # vê tickets/operação (placeholder #1E)


# --- Contratação + Asaas (Spec #2) — armazenados como String+CheckConstraint --


class PlanAudience(StrEnum):
    end_client = "end_client"
    msp = "msp"


class PlanBillingMode(StrEnum):
    subscription = "subscription"
    one_off = "one_off"


class CheckoutStatus(StrEnum):
    started = "started"
    awaiting_payment = "awaiting_payment"
    paid = "paid"
    provisioned = "provisioned"
    failed = "failed"
    expired = "expired"
    canceled = "canceled"


class BillingType(StrEnum):
    """billingType do Asaas (PIX recorrente = subscription com billing_type PIX)."""

    pix = "PIX"
    boleto = "BOLETO"
    credit_card = "CREDIT_CARD"


class PaymentStatus(StrEnum):
    pending = "pending"
    confirmed = "confirmed"
    received = "received"
    overdue = "overdue"
    refunded = "refunded"
    failed = "failed"
    canceled = "canceled"


class ProviderOwnerKind(StrEnum):
    gerti = "gerti"
    msp = "msp"


class ProviderMode(StrEnum):
    sandbox = "sandbox"
    production = "production"


class WebhookEventStatus(StrEnum):
    received = "received"
    processed = "processed"
    failed = "failed"
