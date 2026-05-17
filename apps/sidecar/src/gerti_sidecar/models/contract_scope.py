"""ContractScopeService + ContractScopeCi (Spec #0 §4)."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Date, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base


class ContractScopeService(Base):
    __tablename__ = "contract_scope_service"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.contract.id", ondelete="CASCADE"),
        primary_key=True,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.service_catalog_item.id"),
        primary_key=True,
    )
    unit_price_override: Mapped[float | None] = mapped_column(Numeric(14, 2))


class ContractScopeCi(Base):
    __tablename__ = "contract_scope_ci"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gerti.contract.id", ondelete="CASCADE"),
        primary_key=True,
    )
    znuny_ci_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    covered_from: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    covered_until: Mapped[dt.date | None] = mapped_column(Date)
