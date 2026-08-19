"""Cliente GI da configuração de e-mail do Znuny (T-R9.6, R9 do vídeo).

Duas famílias, e as duas têm op **dedicada** no Perl em vez de passarem pelo
dispatcher genérico. O motivo, nos dois casos, é a mesma coisa: a API nativa
não é segura de expor como está.

**Contas de recebimento (`MailAccount`).** O `MailAccountGet` do Znuny devolve
a senha da caixa em **texto claro**. A op Perl remove o campo antes de
responder, e o `Set` relê a senha atual lá dentro quando o console não manda
uma nova — a senha nunca vai e volta pela rede. Este módulo reforça a mesma
garantia do lado Python: `_strip_secrets` varre a resposta e mata qualquer
chave com cara de senha, em qualquer nível. Redundante de propósito — é o
aceite A9.4, e uma garantia que depende de um único ponto não é garantia.

**Filtros de PostMaster.** A API nativa é por **nome**, não por id, e **não
existe `FilterUpdate`** — atualizar é apagar e recriar. A op Perl faz isso com
guardas de modo (create recusa nome existente, update recusa inexistente) e
devolve o estado anterior completo, para a auditoria registrar antes de sumir.

Reaproveita o transporte de `znuny_admin_objects` (mesma base, mesmo token,
mesmo mapeamento de erro): `ZnunyUnavailable` → 503, `ZnunyWriteError` → 4xx.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gerti_sidecar.integrations.znuny_admin_objects import (
    ZnunyUnavailable,
    ZnunyWriteError,
    _post,
)

__all__ = [
    "MailAccount",
    "PostMasterFilter",
    "ZnunyUnavailable",
    "ZnunyWriteError",
    "delete_postmaster_filter",
    "list_mail_accounts",
    "list_postmaster_filters",
    "set_mail_account",
    "set_postmaster_filter",
]

# Qualquer chave que contenha um destes fragmentos é removida da resposta,
# em qualquer profundidade. Lista de fragmentos, não de nomes exatos: `pw`,
# `Password`, `UserPw`, `pw_hash` — todos morrem aqui.
_SECRET_FRAGMENTS = ("password", "passwd", "senha", "pw", "secret", "token")


def _strip_secrets(value: Any) -> Any:
    """Remove recursivamente qualquer chave com cara de segredo.

    Segunda barreira: a op Perl já não devolve senha. Esta função existe para
    o dia em que alguém acrescentar um campo novo lá e esquecer da guarda —
    o aceite A9.4 diz "nunca aparece em resposta de sistema, tela ou
    auditoria", e três lugares diferentes é exatamente o que ela protege.
    """
    if isinstance(value, dict):
        return {
            k: _strip_secrets(v)
            for k, v in value.items()
            if not any(frag in k.lower() for frag in _SECRET_FRAGMENTS)
        }
    if isinstance(value, list):
        return [_strip_secrets(v) for v in value]
    return value


@dataclass(frozen=True)
class MailAccount:
    """Uma caixa de entrada, e a fila em que as mensagens dela caem."""

    id: int
    login: str
    host: str
    type: str
    valid: bool
    trusted: bool
    dispatching_by: str  # Queue | From
    queue_id: int
    queue_name: str
    comment: str
    imap_folder: str
    # Existe senha guardada? A tela usa isto para mostrar "•••• (mantida)" em
    # vez de um campo vazio, que se leria como "esta conta não tem senha".
    has_password: bool = True


@dataclass(frozen=True)
class FilterPair:
    key: str
    value: str


@dataclass(frozen=True)
class PostMasterFilter:
    """Regra de entrada: o que casar (`match`) e o que marcar (`set`).

    O caso do vídeo (06:19) é `From =~ @cliente.com.br` → `X-OTRS-CustomerNo =
    CLIENTE`: "e-mail deste domínio pertence a este cliente".
    """

    name: str
    stop_after_match: bool
    match: list[FilterPair] = field(default_factory=list)
    set: list[FilterPair] = field(default_factory=list)


def _pairs(raw: Any) -> list[FilterPair]:
    out: list[FilterPair] = []
    for item in raw or []:
        if isinstance(item, dict) and item.get("Key"):
            out.append(FilterPair(key=str(item["Key"]), value=str(item.get("Value") or "")))
    return out


# ── contas de recebimento ───────────────────────────────────────────────────


async def list_mail_accounts(*, agent_login: str) -> list[MailAccount]:
    data = _strip_secrets(await _post("/MailAccount/List", {"AgentLogin": agent_login}))
    out: list[MailAccount] = []
    for r in data.get("Accounts") or []:
        if not isinstance(r, dict) or r.get("ID") is None:
            continue
        out.append(
            MailAccount(
                id=int(r["ID"]),
                login=str(r.get("Login") or ""),
                host=str(r.get("Host") or ""),
                type=str(r.get("Type") or ""),
                valid=str(r.get("ValidID") or "1") == "1",
                trusted=bool(int(r.get("Trusted") or 0)),
                dispatching_by=str(r.get("DispatchingBy") or "Queue"),
                queue_id=int(r.get("QueueID") or 0),
                queue_name=str(r.get("QueueName") or ""),
                comment=str(r.get("Comment") or ""),
                imap_folder=str(r.get("IMAPFolder") or ""),
                has_password=bool(r.get("HasPassword", True)),
            )
        )
    return out


async def set_mail_account(
    *,
    agent_login: str,
    account_id: int | None = None,
    login: str | None = None,
    host: str | None = None,
    type_: str | None = None,
    password: str | None = None,
    valid: bool | None = None,
    trusted: bool | None = None,
    dispatching_by: str | None = None,
    queue_id: int | None = None,
    comment: str | None = None,
    imap_folder: str | None = None,
) -> dict[str, Any]:
    """Cria ou atualiza. `password=None` = **manter a que está lá**.

    Essa distinção é o ponto: o console nunca precisa conhecer a senha atual
    para salvar uma mudança de fila ou de comentário.
    """
    body: dict[str, Any] = {"AgentLogin": agent_login}
    if account_id is not None:
        body["ID"] = account_id
    if login is not None:
        body["Login"] = login
    if host is not None:
        body["Host"] = host
    if type_ is not None:
        body["Type"] = type_
    if password:  # string vazia também significa "não mexer"
        body["Password"] = password
    if valid is not None:
        body["ValidID"] = 1 if valid else 2
    if trusted is not None:
        body["Trusted"] = 1 if trusted else 0
    if dispatching_by is not None:
        body["DispatchingBy"] = dispatching_by
    if queue_id is not None:
        body["QueueID"] = queue_id
    if comment is not None:
        body["Comment"] = comment
    if imap_folder is not None:
        body["IMAPFolder"] = imap_folder
    result: dict[str, Any] = _strip_secrets(await _post("/MailAccount/Set", body))
    return result


# ── filtros de PostMaster (domínios autorizados) ────────────────────────────


async def list_postmaster_filters(*, agent_login: str) -> list[PostMasterFilter]:
    data = await _post("/PostMasterFilter/List", {"AgentLogin": agent_login})
    out: list[PostMasterFilter] = []
    for r in data.get("Filters") or []:
        if not isinstance(r, dict) or not r.get("Name"):
            continue
        out.append(
            PostMasterFilter(
                name=str(r["Name"]),
                stop_after_match=bool(int(r.get("StopAfterMatch") or 0)),
                match=_pairs(r.get("Match")),
                set=_pairs(r.get("Set")),
            )
        )
    return out


async def set_postmaster_filter(
    *,
    agent_login: str,
    name: str,
    match: list[dict[str, str]],
    set_: list[dict[str, str]],
    stop_after_match: bool = False,
    mode: str = "create",
) -> dict[str, Any]:
    result: dict[str, Any] = await _post(
        "/PostMasterFilter/Set",
        {
            "AgentLogin": agent_login,
            "Name": name,
            "Mode": mode,
            "Match": [{"Key": p["key"], "Value": p["value"]} for p in match],
            "Set": [{"Key": p["key"], "Value": p["value"]} for p in set_],
            "StopAfterMatch": 1 if stop_after_match else 0,
        },
    )
    return result


async def delete_postmaster_filter(*, agent_login: str, name: str) -> dict[str, Any]:
    """Apaga de verdade — **exceção declarada** à regra "sem exclusão".

    Filtro de PostMaster não tem `ValidID`: não existe invalidar. A exceção
    vale só para este objeto, e a op devolve o estado anterior completo para a
    auditoria guardá-lo antes de ele sumir.
    """
    result: dict[str, Any] = await _post(
        "/PostMasterFilter/Set",
        {"AgentLogin": agent_login, "Name": name, "Mode": "delete"},
    )
    return result
