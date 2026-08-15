"""GET /v1/search — portal (cliente): busca federada (Spec #3 V6).

tenant-scoped via `get_tenant_session` (RLS). `q` obrigatório, 2-100 chars
(422 fora disso via `Query`). Cada bloco (tickets/assets/kb/catalog) ≤5
itens; cross-tenant é impossível por construção (GI escopado por
`customer_id`/RLS por `tenant_id`).

O bloco de chamados respeita o papel da sessão (#1H): a `SessionPayload` é
repassada inteira para `client_search`, que deriva o escopo do ponto único
`domain.ticket_scope` — o mesmo de `/v1/tickets`. Resultado da busca e
navegação para o detalhe são, por construção, coerentes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.search_service import SearchItem, client_search
from gerti_sidecar.models import Tenant

router = APIRouter(prefix="/search", tags=["portal"])


class SearchItemOut(BaseModel):
    id: str
    title: str
    subtitle: str
    path: str


class SearchResults(BaseModel):
    tickets: list[SearchItemOut]
    assets: list[SearchItemOut]
    kb: list[SearchItemOut]
    catalog: list[SearchItemOut]


def _item(i: SearchItem) -> SearchItemOut:
    return SearchItemOut(id=i.id, title=i.title, subtitle=i.subtitle, path=i.path)


@router.get("", response_model=SearchResults)
async def search(
    request: Request,
    q: str = Query(min_length=2, max_length=100),
    session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> SearchResults:
    tenant: Tenant = request.state.tenant
    results = await client_search(
        session=session,
        session_payload=session_payload,
        customer_id=tenant.znuny_customer_id,
        q=q,
    )
    return SearchResults(
        tickets=[_item(i) for i in results["tickets"]],
        assets=[_item(i) for i in results["assets"]],
        kb=[_item(i) for i in results["kb"]],
        catalog=[_item(i) for i in results["catalog"]],
    )
