import datetime as dt

import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.errors import ContractValidationError
from gerti_sidecar.models.enums import ContractType


@pytest.mark.asyncio
async def test_create_hour_bank_ok_and_validation(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        svc = ContractService(s)
        c = await svc.create(
            NewContract(
                code="CTR-1",
                type=ContractType.hour_bank,
                starts_on=dt.date(2026, 1, 1),
                ends_on=dt.date(2026, 12, 31),
                initial_hours=40,
                unit_price_brl=180,
                billing_period_months=1,
                closing_period_months=3,
                created_by="william",
            )
        )
        assert c.id is not None and c.type == ContractType.hour_bank

        with pytest.raises(ContractValidationError):  # hour_bank requires initial_hours
            await svc.create(
                NewContract(
                    code="CTR-2",
                    type=ContractType.hour_bank,
                    starts_on=dt.date(2026, 1, 1),
                    ends_on=dt.date(2026, 12, 31),
                    created_by="x",
                )
            )

        with pytest.raises(ContractValidationError):  # ends<=starts
            await svc.create(
                NewContract(
                    code="CTR-3",
                    type=ContractType.credit_brl,
                    starts_on=dt.date(2026, 12, 31),
                    ends_on=dt.date(2026, 1, 1),
                    initial_amount_brl=1000,
                    created_by="x",
                )
            )

        with pytest.raises(ContractValidationError):  # duplicate code in tenant
            await svc.create(
                NewContract(
                    code="CTR-1",
                    type=ContractType.credit_brl,
                    starts_on=dt.date(2026, 1, 1),
                    ends_on=dt.date(2026, 12, 31),
                    initial_amount_brl=1000,
                    created_by="x",
                )
            )
