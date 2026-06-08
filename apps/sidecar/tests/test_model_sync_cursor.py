from __future__ import annotations

import pytest

from gerti_sidecar.models import ConsumptionSyncCursor, ZnunyInstance


@pytest.mark.asyncio
async def test_cursor_roundtrip(session):
    inst = ZnunyInstance(
        name="i",
        base_url="http://z",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    cur = ConsumptionSyncCursor(znuny_instance_id=inst.id, last_time_accounting_id=42)
    session.add(cur)
    await session.flush()
    got = await session.get(ConsumptionSyncCursor, inst.id)
    assert got is not None and got.last_time_accounting_id == 42
