"""/v1/admin/znuny/mail-* — configuração de e-mail pelo console (T-R9.6, R9).

*"Se entrou pelo suporte, tem que sair pelo suporte. Se entrou pelo financeiro,
tem que sair pelo financeiro."* (06:38)

Duas superfícies, que juntas são o par entrada/saída do vídeo:

  • `/mail-accounts` — as caixas de RECEBIMENTO e a fila em que cada uma cai.
  • `/postmaster-filters` — os **domínios autorizados**: qual domínio de
    remetente pertence a qual cliente. É a "visão centralizada" de 06:19.

O terceiro lado — o endereço de RESPOSTA por fila — já existe: é o
`SystemAddressID` da fila, exposto pelo `/admin/znuny/objects/Queue` desde a
Onda 0. Por isso este router não o duplica; a tela é que junta os três.

**A senha nunca sai daqui.** A op Perl não a devolve, o cliente GI a remove de
novo, e a auditoria registra só o que mudou. Três barreiras para o mesmo
aceite (A9.4), de propósito.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.domain import audit_service
from gerti_sidecar.integrations import znuny_admin_mail as gi

router = APIRouter(prefix="/admin/znuny", tags=["admin"])

# Nome de filtro vira chave de API no Znuny; restringimos ao que é seguro
# interpolar e legível numa tela.
_FILTER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:-]{0,63}$")


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, gi.ZnunyUnavailable):
        return HTTPException(status_code=503, detail="znuny_unavailable")
    # Recusa limpa do Znuny chega ao operador com a mensagem ORIGINAL (A10.3):
    # "erro genérico" já custou uma onda inteira de diagnóstico nesta campanha.
    return HTTPException(status_code=422, detail=str(exc))


# ── contas de recebimento ───────────────────────────────────────────────────


class MailAccountOut(BaseModel):
    id: int
    login: str
    host: str
    type: str
    valid: bool
    trusted: bool
    dispatching_by: str
    queue_id: int
    queue_name: str
    comment: str
    imap_folder: str
    has_password: bool


class MailAccountIn(BaseModel):
    """Corpo de criação/edição. `password` só vai quando o operador digitou.

    Omitir `password` numa edição significa **manter a que está lá** — e é o
    que permite salvar "mudei a fila desta caixa" sem o console jamais ter
    conhecido a senha.
    """

    model_config = ConfigDict(extra="forbid")

    login: str = Field(max_length=255)
    host: str = Field(max_length=255)
    type: Literal["POP3", "POP3S", "POP3TLS", "IMAP", "IMAPS", "IMAPTLS"] = "IMAPS"
    password: str | None = Field(default=None, max_length=255)
    valid: bool = True
    trusted: bool = False
    dispatching_by: Literal["Queue", "From"] = "Queue"
    queue_id: int = 0
    comment: str = Field(default="", max_length=255)
    imap_folder: str = Field(default="", max_length=255)


@router.get("/mail-accounts")
async def list_mail_accounts(
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[MailAccountOut]:
    try:
        rows = await gi.list_mail_accounts(agent_login=admin["agent_login"])
    except Exception as exc:  # mapeado por _fail: 503 se fora, 422 se recusa
        raise _fail(exc) from exc
    return [MailAccountOut(**vars(r)) for r in rows]


@router.post("/mail-accounts", status_code=201)
async def create_mail_account(
    body: MailAccountIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    if not body.password:
        raise HTTPException(status_code=422, detail="senha é obrigatória ao criar a conta")
    try:
        result = await gi.set_mail_account(
            agent_login=admin["agent_login"],
            login=body.login,
            host=body.host,
            type_=body.type,
            password=body.password,
            valid=body.valid,
            trusted=body.trusted,
            dispatching_by=body.dispatching_by,
            queue_id=body.queue_id,
            comment=body.comment,
            imap_folder=body.imap_folder,
        )
    except Exception as exc:  # mapeado por _fail
        raise _fail(exc) from exc
    await _audit(request, admin, "create", body, result)
    return result


@router.put("/mail-accounts/{account_id}")
async def update_mail_account(
    account_id: int,
    body: MailAccountIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    try:
        result = await gi.set_mail_account(
            agent_login=admin["agent_login"],
            account_id=account_id,
            login=body.login,
            host=body.host,
            type_=body.type,
            password=body.password,  # None/"" => mantém a atual
            valid=body.valid,
            trusted=body.trusted,
            dispatching_by=body.dispatching_by,
            queue_id=body.queue_id,
            comment=body.comment,
            imap_folder=body.imap_folder,
        )
    except Exception as exc:  # mapeado por _fail
        raise _fail(exc) from exc
    await _audit(request, admin, "update", body, result, entity_id=str(account_id))
    return result


async def _audit(
    request: Request,
    admin: AdminSessionPayload,
    action: Literal["create", "update"],
    body: MailAccountIn,
    result: dict[str, Any],
    entity_id: str | None = None,
) -> None:
    # `password` fica FORA do metadata. Registramos apenas SE ela mudou —
    # que é a informação útil numa investigação, sem ser o segredo.
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action=action,
        entity="znuny_mail_account",
        entity_id=entity_id or str(result.get("Account", {}).get("ID") or ""),
        description=f"conta de e-mail {body.login}@{body.host} → fila {body.queue_id}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={
            "login": body.login,
            "host": body.host,
            "type": body.type,
            "queue_id": body.queue_id,
            "dispatching_by": body.dispatching_by,
            "valid": body.valid,
            "password_changed": bool(body.password),
        },
    )


# ── filtros de PostMaster (domínios autorizados) ────────────────────────────


class FilterPairIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(max_length=64)
    value: str = Field(max_length=255)


class PostMasterFilterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=64)
    match: list[FilterPairIn] = Field(min_length=1, max_length=10)
    set: list[FilterPairIn] = Field(min_length=1, max_length=10)
    stop_after_match: bool = False


class FilterPairOut(BaseModel):
    key: str
    value: str


class PostMasterFilterOut(BaseModel):
    name: str
    stop_after_match: bool
    match: list[FilterPairOut]
    set: list[FilterPairOut]


def _check_name(name: str) -> None:
    if not _FILTER_NAME_RE.match(name):
        raise HTTPException(status_code=422, detail="nome de filtro inválido")


@router.get("/postmaster-filters")
async def list_postmaster_filters(
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[PostMasterFilterOut]:
    try:
        rows = await gi.list_postmaster_filters(agent_login=admin["agent_login"])
    except Exception as exc:  # mapeado por _fail
        raise _fail(exc) from exc
    return [
        PostMasterFilterOut(
            name=r.name,
            stop_after_match=r.stop_after_match,
            match=[FilterPairOut(key=p.key, value=p.value) for p in r.match],
            set=[FilterPairOut(key=p.key, value=p.value) for p in r.set],
        )
        for r in rows
    ]


@router.post("/postmaster-filters", status_code=201)
async def create_postmaster_filter(
    body: PostMasterFilterIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    _check_name(body.name)
    return await _save_filter(body, request, admin, mode="create")


@router.put("/postmaster-filters/{name}")
async def update_postmaster_filter(
    name: str,
    body: PostMasterFilterIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    _check_name(name)
    if name != body.name:
        # Renomear é apagar + criar no Znuny; recusamos para não fazer isso
        # por acidente a partir de um formulário de edição.
        raise HTTPException(status_code=422, detail="renomear filtro não é suportado")
    return await _save_filter(body, request, admin, mode="update")


async def _save_filter(
    body: PostMasterFilterIn,
    request: Request,
    admin: AdminSessionPayload,
    *,
    mode: str,
) -> dict[str, Any]:
    try:
        result = await gi.set_postmaster_filter(
            agent_login=admin["agent_login"],
            name=body.name,
            match=[{"key": p.key, "value": p.value} for p in body.match],
            set_=[{"key": p.key, "value": p.value} for p in body.set],
            stop_after_match=body.stop_after_match,
            mode=mode,
        )
    except Exception as exc:  # mapeado por _fail
        raise _fail(exc) from exc
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="create" if mode == "create" else "update",
        entity="znuny_postmaster_filter",
        entity_id=body.name,
        description=f"filtro de e-mail {body.name}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={
            "antes": result.get("Before") or None,
            "depois": {
                "match": [{"key": p.key, "value": p.value} for p in body.match],
                "set": [{"key": p.key, "value": p.value} for p in body.set],
            },
        },
    )
    return result


@router.delete("/postmaster-filters/{name}")
async def delete_postmaster_filter(
    name: str,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    """**Exceção declarada** à regra "sem exclusão" (invariante 3).

    Filtro de PostMaster não tem `ValidID` — não existe invalidar, só apagar. A
    exceção vale só para este objeto, e o estado anterior completo vai para a
    auditoria antes de sumir, para a remoção ser reconstituível.
    """
    _check_name(name)
    try:
        result = await gi.delete_postmaster_filter(agent_login=admin["agent_login"], name=name)
    except Exception as exc:  # mapeado por _fail
        raise _fail(exc) from exc
    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=None,
        action="delete",
        entity="znuny_postmaster_filter",
        entity_id=name,
        description=f"filtro de e-mail {name} REMOVIDO (objeto sem invalidação no Znuny)",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"antes": result.get("Before") or None},
    )
    return result
