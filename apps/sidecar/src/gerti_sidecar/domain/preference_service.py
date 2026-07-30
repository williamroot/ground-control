"""PreferenceService — preferências do usuário no Portal (Spec #3 V3).

`get_or_create` é idempotente: a primeira leitura cria a linha com os
defaults da tabela (gerti.user_preference, UNIQUE (tenant_id, user_login)).
Escrita concorrente na criação é resolvida via savepoint — mesma técnica de
`InvoiceService.create_from_cycle` para a UNIQUE(cycle_id).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.models import UserPreference

# Campos parciais aceitos por `update` — espelha as colunas graváveis da tabela.
_UPDATABLE_FIELDS = (
    "theme",
    "email_notifications",
    "sla_alerts",
    "ticket_updates",
    "contract_alerts",
    "invoice_alerts",
    "weekly_report",
)


class PreferenceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, user_login: str) -> UserPreference:
        existing = await self._find(user_login)
        if existing is not None:
            return existing

        pref = UserPreference(tenant_id=await self._current_tenant_id(), user_login=user_login)
        # Savepoint: colisão de UNIQUE(tenant_id, user_login) sob concorrência
        # não derruba a transação externa (que carrega o GUC app.current_tenant).
        sp = await self.session.begin_nested()
        try:
            self.session.add(pref)
            await self.session.flush()
        except IntegrityError:
            await sp.rollback()
            existing = await self._find(user_login)
            if existing is None:
                raise
            return existing
        return pref

    async def update(self, user_login: str, **fields: Any) -> UserPreference:
        pref = await self.get_or_create(user_login)
        for key in _UPDATABLE_FIELDS:
            if key not in fields:
                continue
            value = fields[key]
            if value is not None:
                setattr(pref, key, value)
        await self.session.flush()
        return pref

    async def _find(self, user_login: str) -> UserPreference | None:
        return (
            await self.session.execute(
                select(UserPreference).where(
                    func.lower(UserPreference.user_login) == user_login.strip().lower()
                )
            )
        ).scalar_one_or_none()

    async def _current_tenant_id(self) -> uuid.UUID:
        res = await self.session.execute(text("SELECT current_setting('app.current_tenant', true)"))
        val = res.scalar_one()
        if not val:
            raise RuntimeError("sessão sem tenant (GUC ausente)")
        return uuid.UUID(val)
