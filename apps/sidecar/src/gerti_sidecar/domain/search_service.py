"""client_search / admin_search — busca federada (Spec #3 V6).

Cliente (`/v1/search`): chamados e ativos vêm do Znuny GI (escopados pelo
`customer_id`/`customer_user` do tenant da sessão); KB e catálogo vêm do
Postgres via a sessão tenant-scoped (RLS) recebida do router — cross-tenant
é portanto impossível por construção (GI escopado + RLS).

O escopo dos CHAMADOS do cliente é decidido por `domain.ticket_scope` — o
MESMO ponto único da lista/detalhe/reply/CSAT em `routers/tickets.py`. Antes
a busca usava `scope="company"` fixo: um helpdesk via título/número/estado de
chamado de colega no resultado e levava 404 ao clicar (a guarda do detalhe já
estava certa). Por isso a busca NÃO recebe `scope` pronto — recebe a
`SessionPayload` e deriva a decisão do mesmo lugar que todo mundo.

Agente (`/v1/admin/search`): cross-tenant por design — tenants (Postgres,
BYPASSRLS), chamados (Znuny GI `Agent/Ticket/Search`, sem filtro de
customer), KB (Postgres, BYPASSRLS).

KB e catálogo são de outro agente da Spec #3 (V1/V2, B1). A busca é
**tolerante**: se o import do model falhar ou a tabela ainda não existir,
o bloco correspondente volta vazio em vez de derrubar a busca inteira.

`path` de cada item já é a rota final pronta (nunca concatenação quebrada).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar import db
from gerti_sidecar.auth.session import SessionPayload
from gerti_sidecar.domain.ticket_scope import ticket_scope
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable
from gerti_sidecar.models import Tenant

MAX_ITEMS = 5


@dataclass(frozen=True)
class SearchItem:
    id: str
    title: str
    subtitle: str
    path: str


def _cap(items: list[SearchItem]) -> list[SearchItem]:
    return items[:MAX_ITEMS]


# --- cliente (tenant-scoped) ------------------------------------------------


async def _search_tickets_client(
    *, session_payload: SessionPayload, customer_id: str, q: str
) -> list[SearchItem]:
    try:
        # MESMA decisão de escopo da lista/detalhe (domain.ticket_scope):
        # helpdesk só acha os próprios chamados; admin do portal, os da empresa.
        rows = await znuny_ticket.search_tickets(
            scope=ticket_scope(session_payload),
            customer_user=session_payload["znuny_login"],
            customer_id=customer_id,
        )
    except ZnunyUnavailable:
        return []
    ql = q.lower()
    matched = [r for r in rows if ql in r.title.lower() or ql in r.ticket_number.lower()]
    return _cap(
        [
            SearchItem(
                id=str(r.znuny_ticket_id),
                title=r.title,
                subtitle=f"#{r.ticket_number} · {r.state}",
                path=f"/tickets/{r.znuny_ticket_id}",
            )
            for r in matched
        ]
    )


async def _search_assets_client(*, customer_id: str, q: str) -> list[SearchItem]:
    try:
        rows = await znuny_ticket.config_item_search(customer_id=customer_id)
    except ZnunyUnavailable:
        return []
    ql = q.lower()
    matched = [r for r in rows if ql in r.name.lower() or ql in r.number.lower()]
    return _cap(
        [
            SearchItem(
                id=str(r.id),
                title=r.name,
                subtitle=f"{r.class_} · {r.deploy_state}",
                path=f"/ativos/{r.id}",
            )
            for r in matched
        ]
    )


async def _search_kb(session: AsyncSession, q: str, *, public_only: bool) -> list[SearchItem]:
    try:
        from gerti_sidecar.models import KbArticle
    except ImportError:
        return []
    try:
        like = f"%{q.lower()}%"
        stmt = select(KbArticle).where(
            or_(
                func.lower(KbArticle.title).like(like),
                func.lower(KbArticle.summary).like(like),
            )
        )
        if public_only:
            stmt = stmt.where(KbArticle.visibility == "public", KbArticle.status == "published")
        rows = (
            (await session.execute(stmt.order_by(KbArticle.updated_at.desc()).limit(MAX_ITEMS)))
            .scalars()
            .all()
        )
    except Exception:
        return []
    if public_only:
        return [
            SearchItem(
                id=str(a.id),
                title=a.title,
                subtitle=a.category,
                path=f"/base-conhecimento/{a.slug}",
            )
            for a in rows
        ]
    return [
        SearchItem(
            id=str(a.id),
            title=a.title,
            subtitle=a.category,
            path=f"/clientes/{a.tenant_id}/conhecimento",
        )
        for a in rows
    ]


async def _search_catalog_client(session: AsyncSession, q: str) -> list[SearchItem]:
    try:
        from gerti_sidecar.models import CatalogItem
    except ImportError:
        return []
    try:
        like = f"%{q.lower()}%"
        rows = (
            (
                await session.execute(
                    select(CatalogItem)
                    .where(
                        CatalogItem.active.is_(True),
                        or_(
                            func.lower(CatalogItem.name).like(like),
                            func.lower(CatalogItem.category).like(like),
                        ),
                    )
                    .order_by(CatalogItem.sort_order, CatalogItem.name)
                    .limit(MAX_ITEMS)
                )
            )
            .scalars()
            .all()
        )
    except Exception:
        return []
    return [
        SearchItem(
            id=str(c.id),
            title=c.name,
            subtitle=c.category,
            path=f"/tickets/novo?servico={c.id}",
        )
        for c in rows
    ]


async def client_search(
    *, session: AsyncSession, session_payload: SessionPayload, customer_id: str, q: str
) -> dict[str, list[SearchItem]]:
    return {
        "tickets": await _search_tickets_client(
            session_payload=session_payload, customer_id=customer_id, q=q
        ),
        "assets": await _search_assets_client(customer_id=customer_id, q=q),
        "kb": await _search_kb(session, q, public_only=True),
        "catalog": await _search_catalog_client(session, q),
    }


# --- agente (cross-tenant) ---------------------------------------------------


async def _search_tenants_admin(session: AsyncSession, q: str) -> list[SearchItem]:
    like = f"%{q.lower()}%"
    rows = (
        (
            await session.execute(
                select(Tenant)
                .where(
                    or_(
                        func.lower(Tenant.trade_name).like(like),
                        func.lower(Tenant.legal_name).like(like),
                        func.lower(Tenant.subdomain).like(like),
                    )
                )
                .order_by(Tenant.trade_name)
                .limit(MAX_ITEMS)
            )
        )
        .scalars()
        .all()
    )
    return [
        SearchItem(id=str(t.id), title=t.trade_name, subtitle=t.subdomain, path=f"/clientes/{t.id}")
        for t in rows
    ]


async def _search_tickets_admin(q: str) -> list[SearchItem]:
    try:
        rows = await znuny_ticket.agent_search(query=q, customer_id=None)
    except ZnunyUnavailable:
        return []
    return _cap(
        [
            SearchItem(
                id=str(r.znuny_ticket_id),
                title=r.title,
                subtitle=f"#{r.ticket_number} · {r.customer_id}",
                path=f"/atendimento/{r.znuny_ticket_id}",
            )
            for r in rows
        ]
    )


async def admin_search(*, q: str) -> dict[str, list[SearchItem]]:
    if db.AdminSessionLocal is None:
        return {"tenants": [], "tickets": [], "kb": []}
    async with db.AdminSessionLocal() as session:
        tenants = await _search_tenants_admin(session, q)
        kb = await _search_kb(session, q, public_only=False)
    tickets = await _search_tickets_admin(q)
    return {"tenants": tenants, "tickets": tickets, "kb": kb}


__all__ = ["MAX_ITEMS", "SearchItem", "admin_search", "client_search"]
