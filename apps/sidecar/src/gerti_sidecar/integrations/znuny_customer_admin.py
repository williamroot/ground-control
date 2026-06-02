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

STUB da Fase 0 (T0.2): corpo implementado em T1.B.
"""

from __future__ import annotations


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
    raise NotImplementedError("T1.B: GertiAdmin CustomerCompanyAdd (ADR D19)")


async def create_customer_user(
    *,
    login: str,
    email: str,
    first_name: str,
    last_name: str,
    customer_id: str,
    valid: bool = True,
) -> str:
    raise NotImplementedError("T1.B: GertiAdmin CustomerUserAdd (ADR D19)")


async def set_password(login: str, password: str) -> None:
    raise NotImplementedError("T1.B: GertiAdmin CustomerUser SetPassword (ADR D19)")
