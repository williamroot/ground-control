"""Cliente GI de ticket (Spec #1E). Escrita/leitura de ticket no Znuny via o
webservice custom GertiTicket (mesmo padrão de znuny_customer_admin.py): base
ZNUNY_ADMIN_WS_URL com path /Webservice/GertiTicket; AccessToken = ZNUNY_WS_TOKEN
no corpo JSON. Erros REUSADOS de znuny_customer_admin (ZnunyUnavailable -> 503,
ZnunyWriteError -> 4xx). Corpo preenchido na Task 7; assinaturas congeladas aqui
para a Fase 1 (Znuny) e a Fase 3 (portal) não divergirem.

Convenção de URL: o webservice GertiTicket é servido na MESMA URL base do
GertiAdmin trocando o último segmento. Resolve-se de ZNUNY_TICKET_WS_URL se
presente, senão deriva de ZNUNY_ADMIN_WS_URL trocando '/GertiAdmin' por
'/GertiTicket' (deploy injeta ZNUNY_TICKET_WS_URL explícito na Fase 4).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from gerti_sidecar.integrations.znuny_customer_admin import (
    ZnunyUnavailable,
    ZnunyWriteError,
)

__all__ = [
    "AgentTicketSummary",
    "Attachment",
    "TicketCreated",
    "TicketDetail",
    "TicketSummary",
    "TimeAccountingPage",
    "TimeEntry",
    "ZnunyUnavailable",
    "ZnunyWriteError",
    "agent_get",
    "agent_search",
    "create_ticket",
    "form_meta",
    "get_ticket",
    "reply_ticket",
    "search_tickets",
    "time_accounting_add",
    "time_accounting_since",
]

_TIMEOUT = 15.0


@dataclass(frozen=True)
class TicketCreated:
    znuny_ticket_id: int
    ticket_number: str


@dataclass(frozen=True)
class TicketSummary:
    znuny_ticket_id: int
    ticket_number: str
    title: str
    state: str
    created: str
    contract_id: str | None


@dataclass(frozen=True)
class TicketDetail:
    znuny_ticket_id: int
    ticket_number: str
    title: str
    state: str
    priority: str
    created: str
    contract_id: str | None
    customer_id: str
    articles: list[dict[str, Any]]


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    content_base64: str


@dataclass(frozen=True)
class TimeEntry:
    id: int
    ticket_id: int
    article_id: int | None
    time_unit: float
    created: str


@dataclass(frozen=True)
class TimeAccountingPage:
    entries: list[TimeEntry]
    max_id: int


@dataclass(frozen=True)
class AgentTicketSummary:
    znuny_ticket_id: int
    ticket_number: str
    title: str
    state: str
    customer_id: str
    owner: str
    created: str


async def time_accounting_since(*, since_id: int, limit: int = 500) -> TimeAccountingPage:
    data = await _post("/TimeAccounting/Since", {"SinceId": since_id, "Limit": limit})
    rows = data.get("Entries") or []
    entries = [
        TimeEntry(
            id=int(r["Id"]),
            ticket_id=int(r["TicketId"]),
            article_id=(
                int(r["ArticleId"]) if r.get("ArticleId") not in (None, "", 0, "0") else None
            ),
            time_unit=float(r.get("TimeUnit") or 0),
            created=str(r.get("Created") or ""),
        )
        for r in rows
        if r.get("Id") is not None
    ]
    return TimeAccountingPage(entries=entries, max_id=int(data.get("MaxId") or since_id))


async def create_ticket(
    *,
    customer_user: str,
    customer_id: str,
    title: str,
    body: str,
    service: str | None,
    type_: str | None,
    priority: str | None,
    contract_id: str,
    attachments: list[Attachment] | None = None,
) -> TicketCreated:
    payload: dict[str, Any] = {
        "CustomerUser": customer_user,
        "CustomerID": customer_id,
        "Title": title,
        "Body": body,
        "ContractId": contract_id,
    }
    if service:
        payload["Service"] = service
    if type_:
        payload["Type"] = type_
    if priority:
        payload["Priority"] = priority
    if attachments:
        payload["Attachments"] = [
            {
                "Filename": a.filename,
                "ContentType": a.content_type,
                "ContentBase64": a.content_base64,
            }
            for a in attachments
        ]
    data = await _post("/Ticket", payload)
    if data.get("TicketID") is None or data.get("TicketNumber") is None:
        raise ZnunyUnavailable("resposta inesperada do Znuny")
    return TicketCreated(int(data["TicketID"]), str(data["TicketNumber"]))


async def search_tickets(
    *,
    scope: str,  # "own" | "company"
    customer_user: str,
    customer_id: str,
) -> list[TicketSummary]:
    data = await _post(
        "/Ticket/Search",
        {"Scope": scope, "CustomerUser": customer_user, "CustomerID": customer_id},
    )
    rows = data.get("Tickets") or []
    return [
        TicketSummary(
            znuny_ticket_id=int(r["TicketID"]),
            ticket_number=str(r.get("TicketNumber") or ""),
            title=str(r.get("Title") or ""),
            state=str(r.get("State") or ""),
            created=str(r.get("Created") or ""),
            contract_id=(str(r["ContractId"]) if r.get("ContractId") else None),
        )
        for r in rows
        if r.get("TicketID") is not None
    ]


async def get_ticket(*, znuny_ticket_id: int, customer_id: str) -> TicketDetail:
    data = await _post("/Ticket/Get", {"TicketID": znuny_ticket_id, "CustomerID": customer_id})
    if data.get("TicketID") is None:
        raise ZnunyUnavailable("resposta inesperada do Znuny")
    return TicketDetail(
        znuny_ticket_id=int(data["TicketID"]),
        ticket_number=str(data.get("TicketNumber") or ""),
        title=str(data.get("Title") or ""),
        state=str(data.get("State") or ""),
        priority=str(data.get("Priority") or ""),
        created=str(data.get("Created") or ""),
        contract_id=(str(data["ContractId"]) if data.get("ContractId") else None),
        customer_id=str(data.get("CustomerID") or ""),
        articles=list(data.get("Articles") or []),
    )


async def reply_ticket(
    *, znuny_ticket_id: int, customer_user: str, customer_id: str, body: str
) -> None:
    await _post(
        "/Ticket/Reply",
        {
            "TicketID": znuny_ticket_id,
            "CustomerUser": customer_user,
            "CustomerID": customer_id,
            "Body": body,
        },
    )


async def form_meta(*, customer_user: str) -> dict[str, list[dict[str, Any]]]:
    data = await _post("/FormMeta", {"CustomerUser": customer_user})
    return {
        "services": list(data.get("Services") or []),
        "priorities": list(data.get("Priorities") or []),
        "types": list(data.get("Types") or []),
    }


async def time_accounting_add(
    *, znuny_ticket_id: int, agent_login: str, time_unit: float, note: str | None = None
) -> None:
    payload: dict[str, Any] = {
        "TicketID": znuny_ticket_id,
        "AgentLogin": agent_login,
        "TimeUnit": time_unit,
    }
    if note:
        payload["Note"] = note
    await _post_agent("/TimeAccounting/Add", payload)


async def agent_search(*, query: str | None, customer_id: str | None) -> list[AgentTicketSummary]:
    body: dict[str, Any] = {}
    if query:
        body["Query"] = query
    if customer_id:
        body["CustomerID"] = customer_id
    data = await _post_agent("/Agent/Ticket/Search", body)
    rows = data.get("Tickets") or []
    return [
        AgentTicketSummary(
            znuny_ticket_id=int(r["TicketID"]),
            ticket_number=str(r.get("TicketNumber") or ""),
            title=str(r.get("Title") or ""),
            state=str(r.get("State") or ""),
            customer_id=str(r.get("CustomerID") or ""),
            owner=str(r.get("Owner") or ""),
            created=str(r.get("Created") or ""),
        )
        for r in rows
        if r.get("TicketID") is not None
    ]


async def agent_get(*, znuny_ticket_id: int) -> dict[str, Any]:
    return await _post_agent("/Agent/Ticket/Get", {"TicketID": znuny_ticket_id})


def _resolve_ticket_endpoint() -> tuple[str, str]:
    explicit = os.environ.get("ZNUNY_TICKET_WS_URL", "")
    if explicit:
        base = explicit
    else:
        base = os.environ.get("ZNUNY_ADMIN_WS_URL", "").replace("/GertiAdmin", "/GertiTicket")
    token = os.environ.get("ZNUNY_WS_TOKEN", "")
    return base, token


async def _post(route: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST failure-safe para uma Route do GertiTicket (espelha _post do admin)."""
    base, token = _resolve_ticket_endpoint()
    url = base.rstrip("/") + route
    payload = {"AccessToken": token, **body}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise ZnunyUnavailable(str(exc)) from exc
    if resp.status_code >= 500:
        raise ZnunyUnavailable(f"znuny http {resp.status_code}")
    if resp.status_code >= 400:
        raise ZnunyWriteError(_err(_safe_json(resp)) or f"znuny http {resp.status_code}")
    data = _safe_json(resp)
    if data is None:
        raise ZnunyUnavailable("resposta não-JSON do Znuny")
    if "Error" in data:
        raise ZnunyWriteError(_err(data) or "znuny rejeitou a operação")
    return data


async def _post_agent(route: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST às ops de agente #1J — espelha _post mas usa ZNUNY_AGENT_WS_TOKEN."""
    base, _ = _resolve_ticket_endpoint()
    token = os.environ.get("ZNUNY_AGENT_WS_TOKEN", "")
    url = base.rstrip("/") + route
    payload = {"AccessToken": token, **body}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise ZnunyUnavailable(str(exc)) from exc
    if resp.status_code >= 500:
        raise ZnunyUnavailable(f"znuny http {resp.status_code}")
    if resp.status_code >= 400:
        raise ZnunyWriteError(_err(_safe_json(resp)) or f"znuny http {resp.status_code}")
    data = _safe_json(resp)
    if data is None:
        raise ZnunyUnavailable("resposta não-JSON do Znuny")
    if "Error" in data:
        raise ZnunyWriteError(_err(data) or "znuny rejeitou a operação")
    return data


def _safe_json(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _err(data: dict[str, Any] | None) -> str:
    if not data:
        return ""
    e = data.get("Error")
    if isinstance(e, dict):
        return str(e.get("ErrorMessage") or e.get("ErrorCode") or "znuny error")
    return str(e) if e else ""
