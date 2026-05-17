"""create gerti.* enum types for the contract domain

Revision ID: 0004_contract_enums
Revises: 0003_force_rls_tenant
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_contract_enums"
down_revision: str | None = "0003_force_rls_tenant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUMS = {
    "contract_type": (
        "closed_value",
        "credit_brl",
        "credit_shared",
        "hour_bank",
        "saas_product",
        "service_count",
    ),
    "contract_status": ("draft", "active", "suspended", "expired", "terminated"),
    "cycle_kind": ("billing", "closing"),
    "cycle_status": ("open", "closed", "invoiced"),
    "glosa_status": ("pending", "approved", "rejected"),
    "billing_status": ("pending", "approved", "billed", "disputed"),
}


def upgrade() -> None:
    for name, values in _ENUMS.items():
        vals = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE gerti.{name} AS ENUM ({vals})")


def downgrade() -> None:
    for name in _ENUMS:
        op.execute(f"DROP TYPE IF EXISTS gerti.{name}")
