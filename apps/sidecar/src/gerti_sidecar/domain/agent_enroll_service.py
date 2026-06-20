"""AgentEnrollService (Spec #1R-a) — enroll/guardrails/heartbeat + approve.

O CORAÇÃO de segurança do #1R: o `customer_id` passado à GI de escrita vem SEMPRE
do tenant DONO DO TOKEN (`tenant.znuny_customer_id`), resolvido server-side sob a
sessão tenant-scoped (RLS) — NUNCA do input do agente. Token do tenant A é
estruturalmente incapaz de escrever em B.

Opera sob `tenant_session_scope(tenant_id)` (RLS-subject): toda query/escrita já
está confinada ao tenant do GUC. O tenant é resolvido pela única linha de
`gerti.tenant` visível (RLS por `id == current_tenant`).

Travas híbridas anti-token-vazado:
- dedupe por (tenant, fingerprint): re-enroll da mesma máquina atualiza (rotaciona
  secret, mantém config_item_id), NÃO duplica, NÃO incrementa registration_count.
- token sem registros disponíveis (max_registrations atingido) OU expirado → device
  novo entra `pending` (NÃO escreve no CMDB) até `approve()` no console.

Credenciais nunca em plaintext: token e agent_secret guardados só como sha256;
verificação constant-time (`agent_secrets.verify`).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.agent_secrets import hash_token, new_agent_secret, verify
from gerti_sidecar.domain.errors import AgentRevoked, EnrollError, EnrollTokenInvalid
from gerti_sidecar.models import AgentEnrollToken, DeviceAgent, Tenant

# Atributos do CI no CMDB (mapeados das specs do agente). Só estes chegam ao
# Znuny — chaves desconhecidas são ignoradas (defesa contra injeção de campo).
_SPEC_TO_ATTR = {
    "operating_system": "OperatingSystem",
    "cpu": "CPU",
    "memory": "Memoria",
    "disk": "Disco",
    "serial": "SerialNumber",
    "vendor": "Vendor",
    "model": "Model",
}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _specs_to_attributes(specs: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, attr in _SPEC_TO_ATTR.items():
        v = specs.get(key)
        if v is not None and str(v) != "":
            out[attr] = str(v)
    return out


class AgentEnrollService:
    def __init__(self, session: AsyncSession, gi: Any) -> None:
        self._session = session
        self._gi = gi

    async def _resolve_tenant(self) -> Tenant:
        """Tenant do GUC corrente (única linha visível sob RLS) — server-trusted."""
        tenant = (await self._session.execute(select(Tenant))).scalars().first()
        if tenant is None:
            raise EnrollError("tenant não resolvido (GUC ausente)")
        return tenant

    async def _write_cmdb(self, tenant: Tenant, device: DeviceAgent) -> tuple[int, str]:
        """Cria/atualiza o CI no CMDB com o customer_id do TENANT (anti-IDOR)."""
        result: tuple[int, str] = await self._gi.config_item_upsert(
            customer_id=tenant.znuny_customer_id,
            name=device.hostname,
            fingerprint=device.fingerprint,
            attributes=_specs_to_attributes(device.specs or {}),
            config_item_id=device.znuny_config_item_id,
        )
        return result

    async def enroll(
        self,
        *,
        token: str,
        fingerprint: str,
        hostname: str,
        os: str | None,
        specs: dict[str, Any],
    ) -> tuple[DeviceAgent, str]:
        """Registra (ou re-registra) um equipamento. Retorna (device, agent_secret_plain)."""
        tenant = await self._resolve_tenant()

        tok = (
            await self._session.execute(
                select(AgentEnrollToken).where(AgentEnrollToken.token_hash == hash_token(token))
            )
        ).scalar_one_or_none()
        # token inexistente/desabilitado → 401 (estruturalmente inválido).
        if tok is None or not tok.enabled:
            raise EnrollTokenInvalid("enroll token inválido")

        secret_plain, secret_hash = new_agent_secret()
        now = _now()

        existing = (
            await self._session.execute(
                select(DeviceAgent).where(DeviceAgent.fingerprint == fingerprint)
            )
        ).scalar_one_or_none()

        if existing is not None:
            # ── Re-enroll: dedupe por fingerprint. Rotaciona secret, atualiza
            #    specs/host/os, mantém config_item_id. NÃO incrementa o contador.
            existing.agent_secret_hash = secret_hash
            existing.hostname = hostname
            existing.os = os
            existing.specs = specs
            existing.last_seen_at = now
            existing.enrolled_at = now
            existing.updated_at = now
            # Reativa um device que estava revogado/pending só se ainda houver
            # quota — caso contrário permanece pending.
            if existing.status == "active" and existing.znuny_config_item_id is not None:
                cid, _ = await self._write_cmdb(tenant, existing)
                existing.znuny_config_item_id = cid
            elif self._has_quota(tok):
                existing.status = "active"
                cid, _ = await self._write_cmdb(tenant, existing)
                existing.znuny_config_item_id = cid
                tok.registration_count += 1
            else:
                existing.status = "pending"
            await self._session.flush()
            return existing, secret_plain

        # ── Device novo: guardrails (quota + expiração) decidem active vs pending.
        active = self._has_quota(tok) and not self._is_expired(tok, now)
        device = DeviceAgent(
            tenant_id=tenant.id,
            fingerprint=fingerprint,
            agent_secret_hash=secret_hash,
            status="active" if active else "pending",
            hostname=hostname,
            os=os,
            specs=specs,
            last_seen_at=now,
            enrolled_at=now,
        )
        self._session.add(device)
        await self._session.flush()

        if active:
            cid, _ = await self._write_cmdb(tenant, device)
            device.znuny_config_item_id = cid
            tok.registration_count += 1
            await self._session.flush()

        return device, secret_plain

    @staticmethod
    def _has_quota(tok: AgentEnrollToken) -> bool:
        if tok.max_registrations is None:
            return True
        return tok.registration_count < tok.max_registrations

    @staticmethod
    def _is_expired(tok: AgentEnrollToken, now: dt.datetime) -> bool:
        return tok.expires_at is not None and tok.expires_at <= now

    async def heartbeat(self, *, agent_secret: str, specs: dict[str, Any]) -> DeviceAgent:
        """Atualiza last_seen; re-sync CMDB se as specs mudaram (e há CI)."""
        tenant = await self._resolve_tenant()
        secret_h = hash_token(agent_secret)
        device = (
            await self._session.execute(
                select(DeviceAgent).where(DeviceAgent.agent_secret_hash == secret_h)
            )
        ).scalar_one_or_none()
        # Defesa adicional: confirma o hash em tempo constante (mesmo já tendo
        # buscado por igualdade — mantém a invariante de verificação central).
        if device is None or not verify(agent_secret, device.agent_secret_hash):
            raise EnrollTokenInvalid("agent secret desconhecido")
        if device.status == "revoked":
            raise AgentRevoked("device revogado")

        now = _now()
        device.last_seen_at = now
        changed = (device.specs or {}) != specs
        device.specs = specs
        device.updated_at = now
        if changed and device.status == "active" and device.znuny_config_item_id is not None:
            cid, _ = await self._write_cmdb(tenant, device)
            device.znuny_config_item_id = cid
        await self._session.flush()
        return device

    async def approve(self, *, device_id: uuid.UUID) -> DeviceAgent:
        """Aprova um device pending no console: escreve no CMDB e ativa."""
        tenant = await self._resolve_tenant()
        device = (
            await self._session.execute(select(DeviceAgent).where(DeviceAgent.id == device_id))
        ).scalar_one_or_none()
        if device is None:
            raise EnrollError("device não encontrado")
        if device.status == "active":
            return device
        if device.status == "revoked":
            raise AgentRevoked("device revogado")
        cid, _ = await self._write_cmdb(tenant, device)
        device.znuny_config_item_id = cid
        device.status = "active"
        device.updated_at = _now()
        await self._session.flush()
        return device

    async def revoke(self, *, device_id: uuid.UUID) -> DeviceAgent:
        """Revoga um device: heartbeats subsequentes recebem 401."""
        device = (
            await self._session.execute(select(DeviceAgent).where(DeviceAgent.id == device_id))
        ).scalar_one_or_none()
        if device is None:
            raise EnrollError("device não encontrado")
        device.status = "revoked"
        device.updated_at = _now()
        await self._session.flush()
        return device
