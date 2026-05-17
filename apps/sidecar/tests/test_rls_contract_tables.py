"""Contract RLS: unprivileged role, fail-closed on unset GUC, cross-tenant blocked."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from gerti_sidecar import db
from gerti_sidecar.models import Contract, Tenant, ZnunyInstance
from gerti_sidecar.models.enums import ContractType


async def _seed_contract(session, tenant_id, code):
    c = Contract(
        tenant_id=tenant_id,
        code=code,
        type=ContractType.credit_brl,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_amount_brl=10000,
        created_by="seed",
    )
    session.add(c)
    await session.flush()
    return c.id


@pytest.mark.asyncio
async def test_contract_rls(session, app_session_factory, seed_two_tenants):
    a_id, b_id = seed_two_tenants
    await _seed_contract(session, a_id, "A-1")
    await _seed_contract(session, b_id, "B-1")
    await session.commit()

    # tenant A scope → only A's contract
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        codes = (await s.execute(text("SELECT code FROM gerti.contract"))).scalars().all()
    assert codes == ["A-1"]

    # tenant B scope → only B's
    async with db.tenant_session_scope(b_id, factory=app_session_factory) as s:
        codes = (await s.execute(text("SELECT code FROM gerti.contract"))).scalars().all()
    assert codes == ["B-1"]

    # unset GUC → zero rows (fail-closed, no empty escape)
    async with app_session_factory() as s:
        rows = (await s.execute(text("SELECT code FROM gerti.contract"))).scalars().all()
    assert rows == []

    # WITH CHECK: inserting a row for another tenant under A's GUC is rejected
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        with pytest.raises(Exception):  # noqa: B017  (RLS WITH CHECK violation)
            await s.execute(
                text(
                    "INSERT INTO gerti.contract "
                    "(tenant_id, code, type, starts_on, ends_on, created_by) "
                    "VALUES (:t, 'X', 'credit_brl', '2026-01-01', '2026-12-31', 's')"
                ),
                {"t": str(b_id)},
            )


@pytest.mark.asyncio
async def test_every_gerti_table_has_rls_enabled_and_forced(session):
    """S1: relrowsecurity AND relforcerowsecurity true for every gerti.* base
    table. Skips until the full chain (ticket_contract_link from 0008) exists
    so per-task gates stay green; HARD-asserts at full-suite & prod (D4)."""
    has_final = (
        await session.execute(text("SELECT to_regclass('gerti.ticket_contract_link') IS NOT NULL"))
    ).scalar_one()
    if not has_final:
        pytest.skip("chain not yet at 0008 — S1 enforced at full suite/prod")
    expected = {
        "tenant",
        "znuny_instance",
        "contract",
        "contract_billing_party",
        "service_catalog_item",
        "shared_credit_pool",
        "contract_scope_service",
        "contract_scope_ci",
        "contract_cycle",
        "consumption_event",
        "glosa",
        "contract_adjustment_rule",
        "contract_renewal_policy",
        "ticket_contract_link",
    }
    rows = (
        await session.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'gerti' AND c.relkind = 'r'"
            )
        )
    ).all()
    state = {r[0]: (r[1], r[2]) for r in rows}
    missing = expected - set(state)
    assert not missing, f"gerti tables absent: {missing}"
    unforced = {t for t, (en, fo) in state.items() if t in expected and not (en and fo)}
    assert not unforced, f"RLS not ENABLE+FORCE on: {unforced}"


@pytest.mark.asyncio
async def test_znuny_instance_rls_scoped_by_tenant(session, app_session_factory):
    """Regression guard for the S1 gap (0009): gerti.znuny_instance is now
    RLS ENABLE+FORCE and scoped via gerti.tenant.znuny_instance_id.

    Seeds TWO distinct instances (one per tenant) via the admin `session`
    (BYPASSRLS) so we can prove that under tenant A's scope an unprivileged
    gerti_sidecar session sees ONLY A's instance — never B's — and that an
    unset GUC yields zero instance rows (fail-closed)."""
    inst_a = ZnunyInstance(
        name="inst-A",
        base_url="http://a",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    inst_b = ZnunyInstance(
        name="inst-B",
        base_url="http://b",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add_all([inst_a, inst_b])
    await session.flush()
    a = Tenant(
        legal_name="A SA",
        trade_name="A",
        document="1",
        znuny_customer_id="a",
        znuny_instance_id=inst_a.id,
        subdomain="a",
    )
    b = Tenant(
        legal_name="B SA",
        trade_name="B",
        document="2",
        znuny_customer_id="b",
        znuny_instance_id=inst_b.id,
        subdomain="b",
    )
    session.add_all([a, b])
    await session.commit()

    # tenant A scope → only A's instance (not B's)
    async with db.tenant_session_scope(a.id, factory=app_session_factory) as s:
        names = (await s.execute(text("SELECT name FROM gerti.znuny_instance"))).scalars().all()
    assert names == ["inst-A"]

    # tenant B scope → only B's instance
    async with db.tenant_session_scope(b.id, factory=app_session_factory) as s:
        names = (await s.execute(text("SELECT name FROM gerti.znuny_instance"))).scalars().all()
    assert names == ["inst-B"]

    # unset GUC → zero rows (fail-closed, no empty escape)
    async with app_session_factory() as s:
        rows = (await s.execute(text("SELECT name FROM gerti.znuny_instance"))).scalars().all()
    assert rows == []
