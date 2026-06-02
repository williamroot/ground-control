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


class ZnunyUnavailable(RuntimeError):
    """Falha de transporte ao falar com o Znuny (-> 503 no router)."""


async def authenticate_agent(login: str, password: str) -> bool:
    raise NotImplementedError("T1.A: SessionCreate via GI com UserLogin+Password (ADR D19)")
