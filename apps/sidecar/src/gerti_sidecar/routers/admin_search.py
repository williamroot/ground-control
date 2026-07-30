"""GET /v1/admin/search — console: busca federada cross-tenant (Spec #3 V6).

Sob `get_admin_session`. `q` obrigatório, 2-100 chars (422 fora disso). Cada
bloco (tenants/tickets/kb) ≤5 itens.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.domain.search_service import SearchItem, admin_search

router = APIRouter(prefix="/admin/search", tags=["admin"])


class SearchItemOut(BaseModel):
    id: str
    title: str
    subtitle: str
    path: str


class AdminSearchResults(BaseModel):
    tenants: list[SearchItemOut]
    tickets: list[SearchItemOut]
    kb: list[SearchItemOut]


def _item(i: SearchItem) -> SearchItemOut:
    return SearchItemOut(id=i.id, title=i.title, subtitle=i.subtitle, path=i.path)


@router.get("", response_model=AdminSearchResults)
async def search(
    q: str = Query(min_length=2, max_length=100),
    _admin: AdminSessionPayload = Depends(get_admin_session),
) -> AdminSearchResults:
    results = await admin_search(q=q)
    return AdminSearchResults(
        tenants=[_item(i) for i in results["tenants"]],
        tickets=[_item(i) for i in results["tickets"]],
        kb=[_item(i) for i in results["kb"]],
    )
