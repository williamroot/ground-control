"""Contract + ContractBillingParty (Spec #0 §4)."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base
from gerti_sidecar.models.enums import ContractStatus, ContractType

# H1: native enum defaults MUST be explicitly cast to the gerti.* type.
_contract_type = ENUM(ContractType, name="contract_type", schema="gerti", create_type=False)
_contract_status = ENUM(ContractStatus, name="contract_status", schema="gerti", create_type=False)


class Contract(Base):
    __tablename__ = "contract"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_contract_tenant_id_code"),
        CheckConstraint("ends_on > starts_on", name="ck_contract_dates"),
        CheckConstraint(
            "closing_period_months % billing_period_months = 0 "
            "OR billing_period_months % closing_period_months = 0",
            name="ck_contract_cycle_multiple",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.tenant.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[ContractType] = mapped_column(_contract_type, nullable=False)
    status: Mapped[ContractStatus] = mapped_column(
        _contract_status,
        nullable=False,
        server_default=text("'active'::gerti.contract_status"),  # H1
    )
    starts_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[dt.date] = mapped_column(Date, nullable=False)

    initial_amount_brl: Mapped[float | None] = mapped_column(Numeric(14, 2))
    initial_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    initial_service_count: Mapped[int | None] = mapped_column(Integer)
    unit_price_brl: Mapped[float | None] = mapped_column(Numeric(14, 2))
    travel_franchise_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    billing_period_months: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    closing_period_months: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    billing_in_advance: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    accumulate_balance_between_cycles: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )
    # H3: column only — the FK to gerti.shared_credit_pool is added at the DB
    # level in migration 0006 (Task 5), AFTER that table exists, and the ORM
    # ForeignKey is declared then alongside the ShareCreditPool model. Declaring
    # it here would make Base.metadata unresolvable (NoReferencedTableError)
    # until Task 5, mirroring the same deferral H3 mandates for the migration.
    shared_pool_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),  # H10: advance on any ORM-mediated mutation
    )


class ContractBillingParty(Base):
    __tablename__ = "contract_billing_party"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.contract.id", ondelete="CASCADE"),
        primary_key=True,
    )
    legal_name: Mapped[str] = mapped_column(String, nullable=False)
    document: Mapped[str] = mapped_column(String, nullable=False)
    fiscal_address: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String)
