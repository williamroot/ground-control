"""AgentEnrollService (Spec #1R-a) — enroll/guardrails/heartbeat, anti-IDOR.

Cobre:
1. enroll válido sob limite → device active + chama config_item_upsert (mock),
   registration_count++, retorna (device, agent_secret_plain).
2. re-enroll mesmo fingerprint → rotaciona secret, mantém config_item_id, não
   duplica, NÃO incrementa o contador.
3. max_registrations atingido (fingerprint novo) → device pending, NÃO chama CMDB.
4. token inexistente/!enabled/expirado → EnrollTokenInvalid.
5. heartbeat: device ativo → atualiza last_seen + re-sync CMDB se specs mudaram;
   revoked → AgentRevoked; secret desconhecido → EnrollTokenInvalid.
6. anti-IDOR: o customer_id passado ao CMDB vem SEMPRE do tenant do token.
7. approve(device pending) → escreve no CMDB e vira active.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from sqlalchemy import select

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.agent_enroll_service import AgentEnrollService
from gerti_sidecar.domain.agent_secrets import hash_token
from gerti_sidecar.domain.errors import AgentRevoked, EnrollTokenInvalid
from gerti_sidecar.models import AgentEnrollToken, DeviceAgent


class FakeGI:
    """Captura as chamadas de upsert e devolve ids previsíveis."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._next_id = 100

    async def config_item_upsert(
        self,
        *,
        customer_id: str,
        name: str,
        fingerprint: str,
        attributes: dict[str, Any],
        config_item_id: int | None = None,
        **kw: Any,
    ) -> tuple[int, str]:
        self.calls.append(
            {
                "customer_id": customer_id,
                "name": name,
                "fingerprint": fingerprint,
                "attributes": attributes,
                "config_item_id": config_item_id,
            }
        )
        if config_item_id is not None:
            return config_item_id, "updated"
        cid = self._next_id
        self._next_id += 1
        return cid, "created"


async def _seed_token(
    factory, tenant_id, *, plain="gcat_tok", max_registrations=None, enabled=True, expires_at=None
) -> str:
    async with tenant_session_scope(tenant_id, factory=factory) as s:
        s.add(
            AgentEnrollToken(
                tenant_id=tenant_id,
                token_hash=hash_token(plain),
                label="install",
                max_registrations=max_registrations,
                enabled=enabled,
                expires_at=expires_at,
            )
        )
    return plain


@pytest.mark.asyncio
async def test_enroll_active_writes_cmdb_with_tenant_customer(
    app_session_factory, seed_two_tenants
):
    tenant_id, _ = seed_two_tenants
    plain = await _seed_token(app_session_factory, tenant_id)
    gi = FakeGI()
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        device, secret = await svc.enroll(
            token=plain,
            fingerprint="FP1",
            hostname="aur-nb-1",
            os="Ubuntu",
            specs={"cpu": "i5", "memory": "16 GB"},
        )
        assert device.status == "active"
        assert device.znuny_config_item_id == 100
        assert secret.startswith("gca_")
    # CMDB recebeu o customer_id do TENANT (server-trusted), não do input.
    assert len(gi.calls) == 1
    assert gi.calls[0]["customer_id"] == "a"  # znuny_customer_id do tenant A
    assert gi.calls[0]["fingerprint"] == "FP1"
    # registration_count++ e secret guardado só como hash
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        tok = (await s.execute(select(AgentEnrollToken))).scalar_one()
        assert tok.registration_count == 1
        dev = (await s.execute(select(DeviceAgent))).scalar_one()
        assert dev.agent_secret_hash == hash_token(secret)
        assert dev.agent_secret_hash != secret


@pytest.mark.asyncio
async def test_reenroll_same_fingerprint_rotates_no_duplicate(
    app_session_factory, seed_two_tenants
):
    tenant_id, _ = seed_two_tenants
    plain = await _seed_token(app_session_factory, tenant_id)
    gi = FakeGI()
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        d1, secret1 = await svc.enroll(
            token=plain, fingerprint="FP1", hostname="h", os="x", specs={"a": 1}
        )
        cid1 = d1.znuny_config_item_id
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        d2, secret2 = await svc.enroll(
            token=plain, fingerprint="FP1", hostname="h", os="x", specs={"a": 2}
        )
    assert d2.znuny_config_item_id == cid1  # mantém o CI
    assert secret2 != secret1  # rotaciona
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        devices = (await s.execute(select(DeviceAgent))).scalars().all()
        assert len(devices) == 1  # não duplicou
        tok = (await s.execute(select(AgentEnrollToken))).scalar_one()
        assert tok.registration_count == 1  # re-enroll NÃO incrementa
    # o 2º upsert foi update (config_item_id presente)
    assert gi.calls[1]["config_item_id"] == cid1


@pytest.mark.asyncio
async def test_enroll_over_limit_new_fingerprint_pending_no_cmdb(
    app_session_factory, seed_two_tenants
):
    tenant_id, _ = seed_two_tenants
    plain = await _seed_token(app_session_factory, tenant_id, max_registrations=1)
    gi = FakeGI()
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        d1, _ = await svc.enroll(token=plain, fingerprint="FP1", hostname="h", os="x", specs={})
        assert d1.status == "active"
    assert len(gi.calls) == 1
    # 2º fingerprint estoura o limite → pending, sem CMDB
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        d2, secret2 = await svc.enroll(
            token=plain, fingerprint="FP2", hostname="h2", os="x", specs={}
        )
        assert d2.status == "pending"
        assert d2.znuny_config_item_id is None
        assert secret2.startswith("gca_")  # secret emitido p/ heartbeat futuro
    assert len(gi.calls) == 1  # NÃO chamou o CMDB de novo


@pytest.mark.asyncio
async def test_enroll_unknown_token_invalid(app_session_factory, seed_two_tenants):
    tenant_id, _ = seed_two_tenants
    gi = FakeGI()
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        with pytest.raises(EnrollTokenInvalid):
            await svc.enroll(token="gcat_nope", fingerprint="FP", hostname="h", os="x", specs={})


@pytest.mark.asyncio
async def test_enroll_disabled_token_invalid(app_session_factory, seed_two_tenants):
    tenant_id, _ = seed_two_tenants
    plain = await _seed_token(app_session_factory, tenant_id, enabled=False)
    gi = FakeGI()
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        with pytest.raises(EnrollTokenInvalid):
            await svc.enroll(token=plain, fingerprint="FP", hostname="h", os="x", specs={})


@pytest.mark.asyncio
async def test_enroll_expired_token_pending(app_session_factory, seed_two_tenants):
    """Token expirado: device entra como pending (trava híbrida), sem CMDB."""
    tenant_id, _ = seed_two_tenants
    past = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    plain = await _seed_token(app_session_factory, tenant_id, expires_at=past)
    gi = FakeGI()
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        d, _ = await svc.enroll(token=plain, fingerprint="FP", hostname="h", os="x", specs={})
        assert d.status == "pending"
    assert gi.calls == []


@pytest.mark.asyncio
async def test_heartbeat_active_updates_lastseen_and_resyncs(app_session_factory, seed_two_tenants):
    tenant_id, _ = seed_two_tenants
    plain = await _seed_token(app_session_factory, tenant_id)
    gi = FakeGI()
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        device, secret = await svc.enroll(
            token=plain, fingerprint="FP1", hostname="h", os="x", specs={"cpu": "i5"}
        )
        cid = device.znuny_config_item_id
    # specs mudaram → re-sync CMDB
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        d = await svc.heartbeat(agent_secret=secret, specs={"cpu": "i9"})
        assert d.last_seen_at is not None
    assert gi.calls[-1]["config_item_id"] == cid  # update do mesmo CI
    assert gi.calls[-1]["customer_id"] == "a"  # anti-IDOR


@pytest.mark.asyncio
async def test_heartbeat_unchanged_specs_no_cmdb(app_session_factory, seed_two_tenants):
    tenant_id, _ = seed_two_tenants
    plain = await _seed_token(app_session_factory, tenant_id)
    gi = FakeGI()
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        _, secret = await svc.enroll(
            token=plain, fingerprint="FP1", hostname="h", os="x", specs={"cpu": "i5"}
        )
    calls_after_enroll = len(gi.calls)
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        await svc.heartbeat(agent_secret=secret, specs={"cpu": "i5"})
    assert len(gi.calls) == calls_after_enroll  # specs iguais → sem CMDB


@pytest.mark.asyncio
async def test_heartbeat_revoked_raises(app_session_factory, seed_two_tenants):
    tenant_id, _ = seed_two_tenants
    plain = await _seed_token(app_session_factory, tenant_id)
    gi = FakeGI()
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        device, secret = await svc.enroll(
            token=plain, fingerprint="FP1", hostname="h", os="x", specs={}
        )
        device.status = "revoked"
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        with pytest.raises(AgentRevoked):
            await svc.heartbeat(agent_secret=secret, specs={})


@pytest.mark.asyncio
async def test_heartbeat_unknown_secret_invalid(app_session_factory, seed_two_tenants):
    tenant_id, _ = seed_two_tenants
    gi = FakeGI()
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        with pytest.raises(EnrollTokenInvalid):
            await svc.heartbeat(agent_secret="gca_nope", specs={})


@pytest.mark.asyncio
async def test_approve_pending_writes_cmdb_and_activates(app_session_factory, seed_two_tenants):
    tenant_id, _ = seed_two_tenants
    plain = await _seed_token(app_session_factory, tenant_id, max_registrations=0)
    gi = FakeGI()
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        d, _ = await svc.enroll(token=plain, fingerprint="FP1", hostname="h", os="x", specs={})
        assert d.status == "pending"
        device_id = d.id
    assert gi.calls == []
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        d = await svc.approve(device_id=device_id)
        assert d.status == "active"
        assert d.znuny_config_item_id is not None
    assert len(gi.calls) == 1
    assert gi.calls[0]["customer_id"] == "a"  # anti-IDOR


@pytest.mark.asyncio
async def test_enroll_cannot_cross_tenant(app_session_factory, seed_two_tenants):
    """Token do tenant A nunca escreve em B: o customer_id vem do tenant do token."""
    a, b = seed_two_tenants
    plain_a = await _seed_token(app_session_factory, a, plain="gcat_a")
    gi = FakeGI()
    async with tenant_session_scope(a, factory=app_session_factory) as s:
        svc = AgentEnrollService(s, gi)
        await svc.enroll(token=plain_a, fingerprint="FP", hostname="h", os="x", specs={})
    # mesmo que o agente "quisesse" o customer de B, o service usou o de A:
    assert gi.calls[0]["customer_id"] == "a"
    assert all(c["customer_id"] != "b" for c in gi.calls)
