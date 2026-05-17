"""ContractAdjustmentRule + ContractRenewalPolicy (Spec #0 §4)."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class ContractAdjustmentRule(Base):
    __tablename__ = "contract_adjustment_rule"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.contract.id", ondelete="CASCADE"),
        primary_key=True,
    )
    index_code: Mapped[str] = mapped_column(String, nullable=False)
    cadence_months: Mapped[int] = mapped_column(Integer, nullable=False)
    next_run_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    cap_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    last_applied_on: Mapped[dt.date | None] = mapped_column(Date)
    last_applied_percent: Mapped[float | None] = mapped_column(Numeric(6, 3))


class ContractRenewalPolicy(Base):
    __tablename__ = "contract_renewal_policy"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.contract.id", ondelete="CASCADE"),
        primary_key=True,
    )
    auto_renew: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    notice_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    next_review_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    renewal_term_months: Mapped[int | None] = mapped_column(Integer)
