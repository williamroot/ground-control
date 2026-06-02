"""Resolução do papel do usuário no Portal (Spec #1H).

Lê gerti.portal_user_role (sessão tenant-scoped → RLS já filtra por tenant).
Default least-privilege: usuário não-mapeado ⇒ helpdesk. A consulta é
case-insensitive em customer_login (= claim do JWT, normalmente o e-mail).
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.models import PortalUserRole
from gerti_sidecar.models.enums import PortalRole

logger = logging.getLogger(__name__)


async def resolve_role(session: AsyncSession, customer_login: str) -> PortalRole:
    """Papel do usuário neste tenant; helpdesk se não mapeado (least-privilege).

    Failure-safe: qualquer erro de DB ⇒ helpdesk (nunca eleva privilégio nem
    derruba o login). A sessão DEVE ser tenant-scoped (RLS escopa as linhas).
    """
    try:
        role = await session.scalar(
            select(PortalUserRole.role).where(
                func.lower(PortalUserRole.customer_login) == customer_login.strip().lower()
            )
        )
    except Exception as exc:  # best-effort; least-privilege no erro
        logger.warning("resolução de papel falhou (%s); fallback helpdesk", exc)
        return PortalRole.helpdesk
    return role if role is not None else PortalRole.helpdesk
