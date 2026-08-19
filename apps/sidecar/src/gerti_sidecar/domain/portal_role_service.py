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


async def resolve_role(
    session: AsyncSession, customer_login: str, *aliases: str | None
) -> PortalRole:
    """Papel do usuário neste tenant; helpdesk se não mapeado (least-privilege).

    Aceita **aliases** porque a mesma pessoa pode ser conhecida por mais de um
    identificador: o login curto do Znuny (`eduardo.salvi`) e o e-mail
    (`eduardo.salvi@auroramoveis.com.br`). Antes, o papel era resolvido só pela
    string exata digitada — e a mesma pessoa via coisas diferentes conforme o
    formato que usou para entrar. Defeito real, achado ao vivo na Onda 0 e com
    a causa raiz explicada na Onda 1.

    A comparação é case-insensitive e o **primeiro** identificador que casar
    vence, na ordem em que vieram. Failure-safe: qualquer erro de DB ⇒
    helpdesk (nunca eleva privilégio nem derruba o login). A sessão DEVE ser
    tenant-scoped (RLS escopa as linhas).
    """
    candidates = [c.strip().lower() for c in (customer_login, *aliases) if c and c.strip()]
    # Ordem preservada, sem repetir: o identificador digitado tem prioridade.
    ordered = list(dict.fromkeys(candidates))
    if not ordered:
        return PortalRole.helpdesk

    try:
        rows = (
            await session.execute(
                select(
                    func.lower(PortalUserRole.customer_login),
                    PortalUserRole.role,
                ).where(func.lower(PortalUserRole.customer_login).in_(ordered))
            )
        ).all()
    except Exception as exc:  # best-effort; least-privilege no erro
        logger.warning("resolução de papel falhou (%s); fallback helpdesk", exc)
        return PortalRole.helpdesk

    by_login: dict[str, PortalRole] = {str(login): PortalRole(role) for login, role in rows}
    for candidate in ordered:
        found = by_login.get(candidate)
        if found is not None:
            return found
    return PortalRole.helpdesk
