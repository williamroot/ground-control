"""Cliente GI — auth de AGENTE Znuny (Spec #1G-a, ADR D19).

Contrato CONGELADO no spike R1G:
  authenticate_agent(login, password) -> bool

Mecanismo (PRIMARY, live-proven no spike): operação core `Session::SessionCreate`
com `UserLogin`+`Password` → roteia para `Kernel::System::Auth->Auth` (auth de
AGENTE). Idêntico ao `authenticate_customer` (D14), trocando o campo de login
(`UserLogin` em vez de `CustomerUserLogin`). SEM resolução e-mail→login: agentes
autenticam pelo `login` da tabela `users`, não pelo e-mail.

Semântica failure-safe (igual ao customer-auth):
  • HTTP 2xx + body com `SessionID` → True
  • `Error`/`SessionCreate.AuthFail`/HTTP 4xx → False
  • conexão/timeout/HTTP 5xx → raise ZnunyUnavailable (-> 503 no router)

STUB da Fase 0 (T0.2): corpo implementado em T1.A.
"""

from __future__ import annotations

import os

import httpx


class ZnunyUnavailable(RuntimeError):
    """Falha de transporte ao falar com o Znuny (-> 503 no router)."""


def _resolve_endpoint() -> tuple[str, str]:
    """(url do webservice, token de acesso). Mesma rota Session do customer-auth
    (D14): em dev/test cai no env ZNUNY_WS_URL / ZNUNY_WS_TOKEN."""
    url = os.environ.get("ZNUNY_WS_URL", "")
    token = os.environ.get("ZNUNY_WS_TOKEN", "")
    return url, token


async def authenticate_agent(login: str, password: str) -> bool:
    # Auth de AGENTE: campo `UserLogin` (não `CustomerUserLogin`) e SEM resolução
    # e-mail→login — agentes autenticam pelo `login` da tabela `users`.
    url, token = _resolve_endpoint()
    body = {
        "UserLogin": login,
        "Password": password,
        "AccessToken": token,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
    except httpx.HTTPError as exc:
        raise ZnunyUnavailable(str(exc)) from exc
    if resp.status_code >= 500:
        raise ZnunyUnavailable(f"znuny http {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise ZnunyUnavailable("resposta não-JSON do Znuny") from exc
    return bool(data.get("SessionID")) and "Error" not in data
