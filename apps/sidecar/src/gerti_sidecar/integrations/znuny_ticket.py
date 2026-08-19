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
from dataclasses import dataclass, field
from typing import Any

import httpx

from gerti_sidecar.integrations.znuny_customer_admin import (
    ZnunyUnavailable,
    ZnunyWriteError,
)

__all__ = [
    "AgentTicket",
    "AgentTicketSummary",
    "Article",
    "AssetDetail",
    "AssetSummary",
    "Attachment",
    "TicketCreated",
    "TicketDetail",
    "TicketStats",
    "TicketSummary",
    "TimeAccountingPage",
    "TimeEntry",
    "ZnunyUnavailable",
    "ZnunyWriteError",
    "agent_get",
    "agent_get_thread",
    "agent_search",
    "agent_ticket_update",
    "config_item_get",
    "config_item_search",
    "config_item_upsert",
    "create_ticket",
    "form_meta",
    "get_ticket",
    "reply_ticket",
    "search_tickets",
    "ticket_stats",
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
    # Dono do chamado, vindo do JOIN em `ticket` (T-R2.3). Default "" para não
    # quebrar chamadores/fakes antigos: a op GI passou a devolvê-los na Onda 1.
    customer_id: str = ""
    customer_user_id: str = ""


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


@dataclass(frozen=True)
class Article:
    """Artigo da thread de um ticket (para IA — #1N). role = SenderType do Znuny."""

    role: str  # customer | agent | system
    author: str
    created: str
    subject: str
    body: str


@dataclass(frozen=True)
class AgentTicket:
    """Ticket de agente com a thread completa (artigos) p/ sumarização/resposta (#1N)."""

    znuny_ticket_id: int
    ticket_number: str
    title: str
    state: str
    customer_id: str
    articles: list[Article]


@dataclass(frozen=True)
class TicketStats:
    """Contagens de ticket agregadas por CustomerID (Spec #1O).

    Tudo escopado pelo CustomerID do tenant na op GI /Ticket/Stats (anti-IDOR
    no Perl: nunca conta tickets de outro CustomerID). Failure-soft no domínio.
    """

    by_state: dict[str, int]
    by_priority: dict[str, int]
    by_day: list[dict[str, Any]]
    sla_breached: int
    sla_at_risk: int
    total: int
    # As três dimensões de "principais tipos de chamado" (T-R18b.1). Chegam
    # sempre as três; qual vai para o relatório é a chave REPORT_TOP_DIMENSION.
    # Default vazio: uma imagem Znuny anterior à Onda 3 não devolve os blocos, e
    # isso precisa degradar para "sem dados", nunca levantar exceção.
    by_type: dict[str, int] = field(default_factory=dict)
    by_service: dict[str, int] = field(default_factory=dict)
    by_queue: dict[str, int] = field(default_factory=dict)
    # A "listona de chamados" do fim do relatório (T-R18b.2).
    tickets: list[dict[str, Any]] = field(default_factory=list)
    tickets_truncated: bool = False


@dataclass(frozen=True)
class AssetSummary:
    id: int
    number: str
    class_: str
    name: str
    deploy_state: str
    inci_state: str


@dataclass(frozen=True)
class AssetDetail:
    id: int
    number: str
    class_: str
    name: str
    deploy_state: str
    inci_state: str
    customer_id: str
    created: str
    attributes: dict[str, object]


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
            customer_id=str(r.get("CustomerId") or ""),
            customer_user_id=str(r.get("CustomerUserId") or ""),
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
    config_item_id: int | None = None,
    queue: str | None = None,
    # R7 (Onda 5) — estado inicial. `None` mantém o padrão do Znuny (`new`);
    # um chamado que exige aprovação nasce em `aguardando aprovacao`, que é do
    # tipo `pending reminder` para o relógio de SLA não correr enquanto o
    # cliente decide.
    state: str | None = None,
) -> TicketCreated:
    payload: dict[str, Any] = {
        "CustomerUser": customer_user,
        "CustomerID": customer_id,
        "Title": title,
        "Body": body,
        "ContractId": contract_id,
    }
    # Fila padrão do cliente (T-R5.3). Ausente => TicketCreate.pm cai no 'Raw'
    # histórico; presente => o chamado nasce onde o operador configurou.
    if queue:
        payload["Queue"] = queue
    if state:
        payload["State"] = state
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
    if config_item_id is not None:
        payload["ConfigItemID"] = config_item_id
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


async def get_ticket(
    *, znuny_ticket_id: int, customer_id: str, customer_user: str | None = None
) -> TicketDetail:
    """Detalhe do ticket com guarda de posse no GI (anti-IDOR).

    `customer_id` (empresa) é sempre exigido. `customer_user` é OPCIONAL e
    corresponde ao escopo `own` da lista: quando informado, o GI exige que o
    ticket também seja daquele CustomerUserID, senão devolve o MESMO
    'ticket not found' (ZnunyWriteError -> 404 no router; nunca 403, nunca
    erro distinto — não vaza a existência do chamado). Vazio == ausente:
    a chave simplesmente não é enviada.
    """
    payload: dict[str, Any] = {"TicketID": znuny_ticket_id, "CustomerID": customer_id}
    if customer_user:
        payload["CustomerUserID"] = customer_user
    data = await _post("/Ticket/Get", payload)
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
    *,
    znuny_ticket_id: int,
    customer_user: str,
    customer_id: str,
    body: str,
    customer_user_id: str | None = None,
) -> None:
    """Responde um ticket com guarda de posse no GI (anti-IDOR).

    ATENÇÃO aos dois parâmetros distintos: `customer_user` é o AUTOR da resposta
    (vai como `CustomerUser`, obrigatório, sempre o usuário logado);
    `customer_user_id` é a GUARDA de posse (vai como `CustomerUserID`).

    `customer_id` (empresa) é sempre exigido. `customer_user_id` é OPCIONAL e
    corresponde ao escopo `own` da lista: quando informado, o GI exige que o
    ticket também seja daquele CustomerUserID, senão devolve o MESMO
    'ticket not found' (ZnunyWriteError -> 404 no router; nunca 403, nunca
    erro distinto — não vaza a existência do chamado). Vazio == ausente:
    a chave simplesmente não é enviada.
    """
    payload: dict[str, Any] = {
        "TicketID": znuny_ticket_id,
        "CustomerUser": customer_user,
        "CustomerID": customer_id,
        "Body": body,
    }
    if customer_user_id:
        payload["CustomerUserID"] = customer_user_id
    await _post("/Ticket/Reply", payload)


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


async def agent_ticket_update(
    *,
    ticket_id: int,
    queue: str | None = None,
    state: str | None = None,
    priority: str | None = None,
    owner: str | None = None,
    note: str | None = None,
) -> None:
    """Aplica mudanças de fila/estado/prioridade/dono + nota interna (Spec #1Q).

    Op de agente (token GertiAgent) — usada pelo executor de ações da automação.
    Só envia os campos presentes; o GI aplica os que vierem e cria a nota interna
    se `note` for dado. Nunca toca outro ticket (escopado por TicketID no Perl).
    """
    payload: dict[str, Any] = {"TicketID": ticket_id}
    if queue is not None:
        payload["Queue"] = queue
    if state is not None:
        payload["State"] = state
    if priority is not None:
        payload["Priority"] = priority
    if owner is not None:
        payload["Owner"] = owner
    if note is not None:
        payload["Note"] = note
    await _post_agent("/Agent/Ticket/Update", payload)


async def agent_get_thread(*, znuny_ticket_id: int) -> AgentTicket:
    """Detalhe de ticket de agente mapeado para AgentTicket (thread tipada, #1N).

    Reusa agent_get (que já traz Articles desde o #1J — From/SenderType/Subject/
    Body/CreateTime). Mapeia SenderType -> role ('customer'/'agent'/'system').
    """
    data = await agent_get(znuny_ticket_id=znuny_ticket_id)
    articles = [
        Article(
            role=str(a.get("SenderType") or ""),
            author=str(a.get("From") or ""),
            created=str(a.get("CreateTime") or ""),
            subject=str(a.get("Subject") or ""),
            body=str(a.get("Body") or ""),
        )
        for a in (data.get("Articles") or [])
    ]
    return AgentTicket(
        znuny_ticket_id=int(data.get("TicketID") or znuny_ticket_id),
        ticket_number=str(data.get("TicketNumber") or ""),
        title=str(data.get("Title") or ""),
        state=str(data.get("State") or ""),
        customer_id=str(data.get("CustomerID") or ""),
        articles=articles,
    )


async def config_item_search(*, customer_id: str) -> list[AssetSummary]:
    """Busca Config Items (CMDB) escopados por CustomerCompany (tenant).

    Usa o token de cliente (_post) — o portal lê ativos do próprio tenant.
    """
    data = await _post("/ConfigItem/Search", {"CustomerCompany": customer_id})
    rows = data.get("ConfigItems") or []
    return [
        AssetSummary(
            id=int(r["Id"]),
            number=str(r.get("Number") or ""),
            class_=str(r.get("Class") or ""),
            name=str(r.get("Name") or ""),
            deploy_state=str(r.get("DeplState") or ""),
            inci_state=str(r.get("InciState") or ""),
        )
        for r in rows
        if r.get("Id") is not None
    ]


async def config_item_get(*, config_item_id: int, customer_id: str) -> AssetDetail:
    """Obtém detalhe de um Config Item (CMDB) com guarda de posse (anti-IDOR).

    O GI valida que o CI pertence ao CustomerCompany; ZnunyWriteError se não
    encontrado → router mapeia para 404.
    """
    data = await _post(
        "/ConfigItem/Get",
        {"ConfigItemID": config_item_id, "CustomerCompany": customer_id},
    )
    return AssetDetail(
        id=int(data.get("Id") or config_item_id),
        number=str(data.get("Number") or ""),
        class_=str(data.get("Class") or ""),
        name=str(data.get("Name") or ""),
        deploy_state=str(data.get("DeplState") or ""),
        inci_state=str(data.get("InciState") or ""),
        customer_id=str(data.get("CustomerID") or ""),
        created=str(data.get("Created") or ""),
        attributes=dict(data.get("Attributes") or {}),
    )


async def config_item_upsert(
    *,
    customer_id: str,
    name: str,
    fingerprint: str,
    attributes: dict[str, object],
    depl_state: str = "Production",
    inci_state: str = "Operational",
    config_item_class: str = "Computer",
    config_item_id: int | None = None,
) -> tuple[int, str]:
    """Cria/atualiza um Config Item no CMDB via GI (escrita, Spec #1R-a).

    `customer_id` é o `znuny_customer_id` do tenant DONO do token (resolvido
    server-side no AgentEnrollService) — NUNCA input do agente. O GI Perl valida
    anti-IDOR no modo update (CustomerID atual do CI == CustomerCompany pedido →
    senão NotFound). Sem `config_item_id` = create; com = update (nova versão).

    Usa o token de admin (_post). Retorna (config_item_id, action) onde action é
    'created' ou 'updated'.
    """
    payload: dict[str, Any] = {
        "CustomerCompany": customer_id,
        "ConfigItemClass": config_item_class,
        "Name": name,
        "DeplState": depl_state,
        "InciState": inci_state,
        "Fingerprint": fingerprint,
        "Attributes": dict(attributes),
    }
    if config_item_id is not None:
        payload["ConfigItemID"] = config_item_id
    data = await _post("/ConfigItem/Upsert", payload)
    cid = data.get("ConfigItemID")
    if cid is None:
        raise ZnunyUnavailable("resposta inesperada do Znuny (sem ConfigItemID)")
    return int(cid), str(data.get("Action") or "")


async def ticket_stats(
    *, customer_id: str, since: str, until: str, include_tickets: bool = False
) -> TicketStats:
    """Contagens de ticket agregadas por CustomerID (Spec #1O).

    Usa o token de admin (_post) — o GI escopa por CustomerCompany (anti-IDOR);
    `since`/`until` são timestamps Znuny ('YYYY-MM-DD HH:MM:SS'). Os blocos
    ausentes degradam para vazios (failure-soft no domínio cuida do GI fora do ar).
    """
    data = await _post(
        "/Ticket/Stats",
        {
            "CustomerCompany": customer_id,
            "Since": since,
            "Until": until,
            # Opt-in: só o relatório executivo precisa da listona. O painel de
            # analytics usa a mesma op e pagaria caro por dados que não mostra.
            "IncludeTickets": 1 if include_tickets else 0,
        },
    )
    by_state = {str(k): int(v) for k, v in (data.get("ByState") or {}).items()}
    by_priority = {str(k): int(v) for k, v in (data.get("ByPriority") or {}).items()}
    by_day = [
        {"date": str(r.get("date") or ""), "count": int(r.get("count") or 0)}
        for r in (data.get("ByDay") or [])
    ]
    total = data.get("Total")
    total_int = int(total) if total is not None else sum(by_state.values())
    # Blocos da Onda 3. Ausentes (imagem Znuny antiga) => vazios, sem exceção.
    by_type = {str(k): int(v) for k, v in (data.get("ByType") or {}).items()}
    by_service = {str(k): int(v) for k, v in (data.get("ByService") or {}).items()}
    by_queue = {str(k): int(v) for k, v in (data.get("ByQueue") or {}).items()}
    tickets = [
        {
            "znuny_ticket_id": int(r.get("TicketID") or 0),
            "ticket_number": str(r.get("TicketNumber") or ""),
            "title": str(r.get("Title") or ""),
            "state": str(r.get("State") or ""),
            "priority": str(r.get("Priority") or ""),
            "type": str(r.get("Type") or ""),
            "service": str(r.get("Service") or ""),
            "queue": str(r.get("Queue") or ""),
            "created": str(r.get("Created") or ""),
            "customer_user": str(r.get("CustomerUser") or ""),
            "accounted_time": float(r.get("AccountedTime") or 0),
        }
        for r in (data.get("Tickets") or [])
        if isinstance(r, dict)
    ]
    return TicketStats(
        by_state=by_state,
        by_priority=by_priority,
        by_day=by_day,
        sla_breached=int(data.get("SlaBreached") or 0),
        sla_at_risk=int(data.get("SlaAtRisk") or 0),
        total=total_int,
        by_type=by_type,
        by_service=by_service,
        by_queue=by_queue,
        tickets=tickets,
        tickets_truncated=bool(data.get("TicketsTruncated")),
    )


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
