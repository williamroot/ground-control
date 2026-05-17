"""ContractCycle (Spec #0 §4)."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerti_sidecar.models.base import Base
from gerti_sidecar.models.enums import CycleKind, CycleStatus

_cycle_kind = ENUM(CycleKind, name="cycle_kind", schema="gerti", create_type=False)
_cycle_status = ENUM(CycleStatus, name="cycle_status", schema="gerti", create_type=False)


class ContractCycle(Base):
    __tablename__ = "contract_cycle"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "kind",
            "period_start",
            name="uq_contract_cycle_contract_id_kind_period_start",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gerti.contract.id"), nullable=False
    )
    kind: Mapped[CycleKind] = mapped_column(_cycle_kind, nullable=False)
    period_start: Mapped[dt.date] = mapped_column(Date, nullable=False)
    period_end: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[CycleStatus] = mapped_column(
        _cycle_status,
        nullable=False,
        server_default=text("'open'::gerti.cycle_status"),
    )  # H1
    opened_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    totals: Mapped[dict[str, object] | None] = mapped_column(JSONB)
