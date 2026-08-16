"""Cliente GI de ESCRITA de cliente Znuny (Spec #1G-a, ADR D19).

Contrato CONGELADO no spike R1G. O GI core do Znuny NÃO expõe escrita de
cliente; o mecanismo (Spec #0: só GI, nunca SQL direto) é uma **operação GI
custom** que embrulha a API Perl nativa (`CustomerCompanyAdd`,
`CustomerUserAdd`, `SetPassword`), exposta por um webservice `GertiAdmin`.

Assinaturas congeladas (T1.B preenche o corpo; T1.C consome via interface):
  create_customer_company(customer_id, company_name, *, valid=True) -> str
  create_customer_user(*, login, email, first_name, last_name,
                        customer_id, valid=True) -> str
  set_password(login, password) -> None

Erros:
  • ZnunyUnavailable — transporte/timeout/HTTP 5xx → failure-safe (vira 503).
  • ZnunyWriteError  — rejeição LIMPA do GI (ex.: login já existe) → mapeável a 4xx.

Convenção de URL (escolha única, ADR D19): `ZNUNY_ADMIN_WS_URL` é a base
COMPLETA até `.../Webservice/GertiAdmin` (sem barra final relevante). A URL
final é `ZNUNY_ADMIN_WS_URL.rstrip('/') + Route`, onde Route é `/CustomerCompany`,
`/CustomerUser` ou `/CustomerUser/Password`. O token de acesso reaproveita o
env existente `ZNUNY_WS_TOKEN` e vai no corpo JSON como `AccessToken`. Ambos os
envs são injetados no deploy da Fase 2.

STUB da Fase 0 (T0.2): corpo implementado em T1.B.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

_TIMEOUT = 10.0


def _resolve_admin_endpoint() -> tuple[str, str]:
    """(base do webservice GertiAdmin, token de acesso).

    base = env ZNUNY_ADMIN_WS_URL (até `.../Webservice/GertiAdmin`);
    token = env ZNUNY_WS_TOKEN (reaproveitado). Lidos via os.environ no
    mesmo espírito de znuny_gi._resolve_endpoint.
    """
    base = os.environ.get("ZNUNY_ADMIN_WS_URL", "")
    token = os.environ.get("ZNUNY_WS_TOKEN", "")
    return base, token


async def _post(route: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST failure-safe para uma Route do GertiAdmin.

    Retorna o JSON decodificado em caso de sucesso (2xx, sem `Error`).
    Erros de transporte/timeout/HTTP 5xx/JSON inválido → ZnunyUnavailable.
    HTTP 4xx ou corpo com `Error` → ZnunyWriteError (rejeição limpa).
    """
    base, token = _resolve_admin_endpoint()
    url = base.rstrip("/") + route
    payload = {"AccessToken": token, **body}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise ZnunyUnavailable(str(exc)) from exc
    if resp.status_code >= 500:
        raise ZnunyUnavailable(f"znuny http {resp.status_code}")
    # 4xx é rejeição limpa do GI (validação/duplicado) → write-error.
    if resp.status_code >= 400:
        message = _error_message(_safe_json(resp)) or f"znuny http {resp.status_code}"
        raise ZnunyWriteError(message)
    data = _safe_json(resp)
    if data is None:
        raise ZnunyUnavailable("resposta não-JSON do Znuny")
    if "Error" in data:
        raise ZnunyWriteError(_error_message(data) or "znuny rejeitou a escrita")
    return data


def _safe_json(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _error_message(data: dict[str, Any] | None) -> str:
    """Extrai uma mensagem legível do `Error` do GI (dict ou string)."""
    if not data:
        return ""
    err = data.get("Error")
    if isinstance(err, dict):
        return str(err.get("ErrorMessage") or err.get("ErrorCode") or err or "znuny error")
    if err:
        return str(err)
    return ""


class ZnunyUnavailable(RuntimeError):
    """Falha de transporte ao falar com o Znuny (-> 503)."""


class ZnunyWriteError(RuntimeError):
    """Rejeição limpa do Znuny GI (ex.: duplicado) — mapeável a 4xx, não 503."""


async def create_customer_company(
    customer_id: str,
    company_name: str,
    *,
    valid: bool = True,
) -> str:
    data = await _post(
        "/CustomerCompany",
        {
            "CustomerID": customer_id,
            "CustomerCompanyName": company_name,
            "ValidID": 1 if valid else 2,
        },
    )
    return str(data.get("CustomerID") or customer_id)


async def create_customer_user(
    *,
    login: str,
    email: str,
    first_name: str,
    last_name: str,
    customer_id: str,
    valid: bool = True,
    phone: str | None = None,
    mobile: str | None = None,
) -> str:
    body: dict[str, Any] = {
        "UserLogin": login,
        "UserEmail": email,
        "UserFirstname": first_name,
        "UserLastname": last_name,
        "UserCustomerID": customer_id,
        "ValidID": 1 if valid else 2,
    }
    if phone is not None:
        body["UserPhone"] = phone
    if mobile is not None:
        body["UserMobile"] = mobile
    data = await _post("/CustomerUser", body)
    return str(data.get("UserLogin") or login)


async def set_password(login: str, password: str) -> None:
    await _post(
        "/CustomerUser/Password",
        {"UserLogin": login, "Password": password},
    )


# ── Onda 1 — corrigir o cadastro depois de criado (R1/R2) ────────────────────


async def update_customer_company(
    customer_id: str,
    *,
    company_name: str | None = None,
    street: str | None = None,
    zip_code: str | None = None,
    city: str | None = None,
    country: str | None = None,
    comment: str | None = None,
    valid: bool | None = None,
) -> str:
    """Espelha endereço/contato no `customer_company` nativo (T-R1.3).

    `gerti.tenant` é a **dona** do dado (decisão D-B); isto aqui é o espelho
    best-effort para que o agente que trabalha dentro do painel do Znuny veja o
    mesmo endereço que o operador digitou no console. Campo ausente = não muda
    (a op faz merge sobre o registro atual; o Update nativo é full replace).
    """
    body: dict[str, Any] = {"CustomerID": customer_id}
    if company_name is not None:
        body["CustomerCompanyName"] = company_name
    if street is not None:
        body["CustomerCompanyStreet"] = street
    if zip_code is not None:
        body["CustomerCompanyZIP"] = zip_code
    if city is not None:
        body["CustomerCompanyCity"] = city
    if country is not None:
        body["CustomerCompanyCountry"] = country
    if comment is not None:
        body["CustomerCompanyComment"] = comment
    if valid is not None:
        body["ValidID"] = 1 if valid else 2
    data = await _post("/CustomerCompany/Update", body)
    return str(data.get("CustomerID") or customer_id)


async def update_customer_user(
    login: str,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    mobile: str | None = None,
    valid: bool | None = None,
) -> None:
    """Edita/desativa a pessoa do cliente no Znuny (T-R2.1).

    Desativar é `ValidID = 2` — nunca delete (invariante 3). Senha NÃO passa por
    aqui: a op Perl rejeita qualquer chave com cara de senha, e `set_password` é
    a operação separada e explícita.
    """
    body: dict[str, Any] = {"UserLogin": login}
    if first_name is not None:
        body["UserFirstname"] = first_name
    if last_name is not None:
        body["UserLastname"] = last_name
    if email is not None:
        body["UserEmail"] = email
    if phone is not None:
        body["UserPhone"] = phone
    if mobile is not None:
        body["UserMobile"] = mobile
    if valid is not None:
        body["ValidID"] = 1 if valid else 2
    await _post("/CustomerUser/Update", body)


@dataclass(frozen=True)
class ZnunyCustomerUser:
    """Uma pessoa do cliente, como o Znuny (dono da identidade) a conhece."""

    login: str
    first_name: str
    last_name: str
    email: str
    phone: str
    mobile: str
    active: bool


@dataclass(frozen=True)
class CustomerUserPage:
    """Lista de pessoas + se o Znuny cortou o resultado.

    `truncated` não é detalhe: uma lista cortada em silêncio faz o operador
    concluir que alguém sumiu do cadastro. A op Perl tem teto de 500 e diz
    quando bateu nele; quem consome precisa poder repassar o aviso.
    """

    users: list[ZnunyCustomerUser]
    truncated: bool = False


async def list_customer_users(customer_id: str) -> CustomerUserPage:
    """Pessoas de um CustomerID, ativas **e** desativadas (T-R2.2).

    Fonte de verdade é o Znuny (decisão D-C): quem foi criado direto no painel
    aparece aqui, e por isso deixa de ser invisível no console.
    """
    data = await _post("/CustomerUser/List", {"CustomerID": customer_id})
    rows = data.get("Users") or []
    out: list[ZnunyCustomerUser] = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("UserLogin"):
            continue
        out.append(
            ZnunyCustomerUser(
                login=str(r["UserLogin"]),
                first_name=str(r.get("UserFirstname") or ""),
                last_name=str(r.get("UserLastname") or ""),
                email=str(r.get("UserEmail") or ""),
                phone=str(r.get("UserPhone") or ""),
                mobile=str(r.get("UserMobile") or ""),
                active=str(r.get("ValidID") or "1") == "1",
            )
        )
    return CustomerUserPage(users=out, truncated=str(data.get("Truncated") or "0") == "1")
