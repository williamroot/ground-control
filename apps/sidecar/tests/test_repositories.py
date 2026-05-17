import datetime as dt

import pytest

from gerti_sidecar import db
from gerti_sidecar.models import Contract
from gerti_sidecar.models.enums import ContractType
from gerti_sidecar.repositories.contract import ContractRepository


@pytest.mark.asyncio
async def test_contract_repo_scoped(session, app_session_factory, seed_two_tenants):
    a_id, b_id = seed_two_tenants
    for tid, code in ((a_id, "A1"), (b_id, "B1")):
        session.add(
            Contract(
                tenant_id=tid,
                code=code,
                type=ContractType.credit_brl,
                starts_on=dt.date(2026, 1, 1),
                ends_on=dt.date(2026, 12, 31),
                initial_amount_brl=1000,
                created_by="s",
            )
        )
    await session.commit()

    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        repo = ContractRepository(s)
        rows = await repo.list()
        assert [c.code for c in rows] == ["A1"]
        got = await repo.get_by_code("A1")
        assert got is not None and got.tenant_id == a_id
        assert await repo.get_by_code("B1") is None  # RLS hides B
