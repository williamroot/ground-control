"""Cliente fino do Generic Interface do Znuny — só auth de customer.

Contrato CONGELADO no spike R1 (ADR D14):
  authenticate_customer(login, password) -> bool
  ZnunyUnavailable: só em falha de transporte/5xx (nunca em rejeição limpa).
Endpoint/token vêm da única linha gerti.znuny_instance.

Login SEMPRE por e-mail (requisito de produto): o Znuny GI espera o
`CustomerUserLogin` (campo `login` da tabela `customer_user`), que NEM SEMPRE
é o e-mail (Aurora foi semeado com login=username + e-mail separado). Antes do
SessionCreate, se o valor informado parece um e-mail, resolvemos o `login` real
lendo `public.customer_user` READ-ONLY (SELECT). Resolução é failure-safe: erro
de DB NÃO derruba o login — loga e cai no valor cru (TechNova, cujo login já é
o e-mail, segue funcionando; e um SessionCreate que falhe vira 401 normal).
"""

from __future__ import annotations

import logging
import os

import httpx
from sqlalchemy import text

from gerti_sidecar import db

logger = logging.getLogger(__name__)


class ZnunyUnavailable(RuntimeError):
    """Falha de transporte ao falar com o Znuny (-> 503 no router)."""


def _resolve_endpoint() -> tuple[str, str]:
    """(url do webservice, token de acesso). base_url da gerti.znuny_instance;
    o token concreto é resolvido do secret-ref (vault) — em dev/test cai no
    env ZNUNY_WS_URL / ZNUNY_WS_TOKEN. Implementação exata definida em D14."""
    url = os.environ.get("ZNUNY_WS_URL", "")
    token = os.environ.get("ZNUNY_WS_TOKEN", "")
    return url, token


# Schema da tabela do Znuny. Em prod o Znuny carrega o schema em `public`
# (confirmado: information_schema.tables → public.customer_user) e no dev/test
# a paridade também usa `public`. Detalhe de convergência aceito (Spec #0:
# sidecar lê znuny read-only). Override via env só para casos excepcionais.
_CUSTOMER_USER_TABLE = os.environ.get("ZNUNY_CUSTOMER_USER_TABLE", "public.customer_user")


async def resolve_login_from_email(email: str) -> str:
    """Resolve o `login` real do customer a partir do e-mail (READ-ONLY).

    API pública: usada pelo router de auth para gravar o login canônico do
    Znuny no claim `znuny_login` da sessão JWT.

    SELECT-only em public.customer_user. Failure-safe: qualquer erro (DB
    indisponível, sessão não inicializada, sem grant) cai no valor cru —
    NUNCA derruba o login. Se não há linha casando, também devolve o cru
    (tenant cujo login já É o e-mail segue funcionando).
    """
    factory = db.SessionLocal
    if factory is None:
        logger.warning("resolução e-mail→login: SessionLocal não inicializado; fallback")
        return email
    sql = text(
        f"SELECT login FROM {_CUSTOMER_USER_TABLE} "  # noqa: S608 — tabela é constante de módulo, nunca input
        "WHERE lower(email) = lower(:email) AND valid_id = 1 "
        "ORDER BY login LIMIT 1"
    )
    try:
        async with factory() as session:
            row = (await session.execute(sql, {"email": email})).first()
    except Exception as exc:  # resolução é best-effort (failure-safe)
        logger.warning("resolução e-mail→login falhou (%s); fallback p/ valor cru", exc)
        return email
    if row is not None and row[0]:
        return str(row[0])
    return email


async def resolve_email_from_login(login: str) -> str | None:
    """O caminho INVERSO: e-mail do customer a partir do login (READ-ONLY).

    Existe por causa de um defeito real, achado ao vivo na Onda 0 e explicado
    na Onda 1: `gerti.portal_user_role` pode estar chaveado pelo **e-mail**
    (`eduardo.salvi@auroramoveis.com.br`) enquanto a pessoa entra com o
    **login curto** do Znuny (`eduardo.salvi`). São strings diferentes, não uma
    diferença de caixa — então a mesma pessoa caía no papel default `helpdesk`
    ou no papel `admin` conforme o formato que digitou.

    Com isto, a resolução de papel passa a tentar os dois identificadores.

    Mesmo contrato do irmão `resolve_login_from_email`: SELECT-only, e
    failure-safe — devolve `None` em qualquer erro, nunca derruba o login.
    """
    factory = db.SessionLocal
    if factory is None:
        return None
    sql = text(
        f"SELECT email FROM {_CUSTOMER_USER_TABLE} "  # noqa: S608 — tabela é constante de módulo
        "WHERE lower(login) = lower(:login) LIMIT 1"
    )
    try:
        async with factory() as session:
            row = (await session.execute(sql, {"login": login})).first()
    except Exception as exc:  # best-effort
        logger.warning("resolução login→e-mail falhou (%s); segue sem alias", exc)
        return None
    if row is not None and row[0]:
        return str(row[0])
    return None


async def authenticate_customer(login: str, password: str) -> bool:
    # Login sempre por e-mail: se parece e-mail, resolve o CustomerUserLogin real.
    customer_login = login
    if "@" in login:
        customer_login = await resolve_login_from_email(login)
    url, token = _resolve_endpoint()
    body = {
        "CustomerUserLogin": customer_login,
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
