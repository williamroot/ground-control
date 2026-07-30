"""PreferenceService: get_or_create idempotente (defaults na 1ª leitura),
update parcial (Spec #3 V3).
"""

from __future__ import annotations

import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.preference_service import PreferenceService


@pytest.mark.asyncio
async def test_get_or_create_defaults_and_idempotent(
    session, app_session_factory, seed_two_tenants
):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        svc = PreferenceService(s)
        p1 = await svc.get_or_create("joe@aurora")
        assert p1.theme == "system"
        assert p1.email_notifications is True
        assert p1.weekly_report is False

        # segunda leitura não cria nova linha (mesmo id, mesma UNIQUE)
        p2 = await svc.get_or_create("joe@aurora")
        assert p2.id == p1.id

        # case-insensitive
        p3 = await svc.get_or_create("JOE@AURORA")
        assert p3.id == p1.id


@pytest.mark.asyncio
async def test_update_partial_fields(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        svc = PreferenceService(s)
        await svc.get_or_create("joe@aurora")

        updated = await svc.update("joe@aurora", theme="dark", weekly_report=True)
        assert updated.theme == "dark"
        assert updated.weekly_report is True
        # campos não enviados preservam o default
        assert updated.email_notifications is True
        assert updated.sla_alerts is True

        # None não sobrescreve (equivalente a "campo omitido")
        again = await svc.update("joe@aurora", theme=None, sla_alerts=False)
        assert again.theme == "dark"
        assert again.sla_alerts is False


@pytest.mark.asyncio
async def test_preferences_isolated_per_tenant(session, app_session_factory, seed_two_tenants):
    a_id, b_id = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        await PreferenceService(s).update("joe@shared", theme="dark")

    async with db.tenant_session_scope(b_id, factory=app_session_factory) as s:
        # mesmo login, outro tenant: linha própria com defaults
        pref_b = await PreferenceService(s).get_or_create("joe@shared")
        assert pref_b.theme == "system"
