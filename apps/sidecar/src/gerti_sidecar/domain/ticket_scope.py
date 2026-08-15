# apps/sidecar/src/gerti_sidecar/domain/ticket_scope.py
"""Escopo de visibilidade de chamado por papel do portal (#1H) — PONTO ÚNICO.

admin do portal => 'company' (vê a empresa inteira); qualquer outro papel =>
'own' (só os próprios chamados). **Todo** consumidor de leitura de chamado do
cliente decide o escopo AQUI: lista, detalhe, resposta, CSAT
(`routers/tickets.py`) e busca federada (`domain/search_service.py`).

Quando duas superfícies divergiram, virou IDOR cross-usuário: o detalhe deixava
um helpdesk abrir chamado de colega (T-R2.4) e a busca do portal devolvia
título/número/estado de chamado de colega — que ao ser clicado dava 404, porque
o detalhe já estava correto. Por isso a regra mora num módulo só; qualquer nova
superfície que leia chamado do cliente importa daqui em vez de repetir o `if`.
"""

from __future__ import annotations

from typing import Literal

from gerti_sidecar.auth.session import SessionPayload
from gerti_sidecar.models.enums import PortalRole

TicketScope = Literal["own", "company"]


def ticket_scope(session_payload: SessionPayload) -> TicketScope:
    """Escopo do GI ('own' | 'company') para a sessão de portal informada."""
    return "company" if session_payload["role"] == PortalRole.admin.value else "own"


def own_login(session_payload: SessionPayload) -> str | None:
    """Login a exigir do GI como guarda de posse, ou None no escopo de empresa."""
    return None if ticket_scope(session_payload) == "company" else session_payload["znuny_login"]


__all__ = ["TicketScope", "own_login", "ticket_scope"]
