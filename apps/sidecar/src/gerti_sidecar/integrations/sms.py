"""Envio de SMS com transporte trocável (T-R6.4, decisão I-5).

O provedor ainda não foi escolhido (Twilio é o candidato). Em vez de deixar o
requisito parado esperando a decisão, o SMS é construído **inteiro**, com o
envio atrás de uma interface — e o primeiro transporte é um **mock que imprime
no log**.

Isso não é gambiarra: é a mesma forma dos outros adaptadores do projeto
(`integrations/ollama.py`, `integrations/asaas_client.py` — transporte
injetável, erro tipado). Quando o provedor for escolhido, entra um segundo
transporte e a chave muda; nada mais no fluxo é reescrito.

## O cuidado que vale desde já

**SMS tem custo por mensagem.** O mock esconde isso: é fácil deixar um laço
mandando mil mensagens e só descobrir com o provedor real ligado. Três coisas
protegem contra isso, e as três são testadas:

1. `sms_enabled` desligado ⇒ **zero** envios, não "envio silencioso";
2. o transporte de console **mascara o destinatário** no log — número de
   telefone completo em log de container é dado pessoal vazando;
3. falha de envio **não derruba** a emissão da fatura (best-effort, igual ao
   e-mail): a cobrança é o ato importante, o aviso é acessório.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

logger = logging.getLogger(__name__)

__all__ = ["ConsoleSmsTransport", "SmsTransport", "mask_phone", "send_sms"]


def mask_phone(phone: str) -> str:
    """'+5531999990000' -> '+55319****0000'. Log não é lugar de telefone inteiro."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) <= 8:
        return "*" * len(digits)
    return f"{phone[:6]}****{digits[-4:]}"


class SmsTransport(Protocol):
    async def send(self, *, to: str, body: str) -> None: ...


def console_log_line(to: str, body: str) -> str:
    """A linha de log do transporte simulado — com o telefone MASCARADO.

    Telefone inteiro em log de container é dado pessoal vazando, e o log do
    modo simulado é justamente o que alguém vai ler para conferir o envio.
    """
    return (
        f"sms.console to={mask_phone(to)} body={body[:80]!r} "
        "(modo simulado — nenhuma mensagem real enviada)"
    )


class ConsoleSmsTransport:
    """Transporte padrão: registra no log o que teria saído.

    Visível com `docker compose logs sidecar`. O destinatário vai mascarado e o
    corpo é truncado — o log precisa provar que a mensagem saiu, não guardar o
    conteúdo dela.
    """

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        # A linha exata que foi para o log. Existe para o teste poder afirmar
        # que o número sai MASCARADO sem depender da configuração global de
        # logging — que, com a ordem de testes aleatória, nem sempre está
        # ligada quando o teste roda.
        self.log_lines: list[str] = []

    async def send(self, *, to: str, body: str) -> None:
        self.sent.append((to, body))
        line = console_log_line(to, body)
        self.log_lines.append(line)
        logger.info("%s", line)


def _transport() -> SmsTransport:
    """Escolhe o transporte pela chave `SMS_PROVIDER`.

    `console` (padrão) = mock. Quando o provedor real existir, este é o único
    lugar que muda — mais a chave no `.env.prod`.
    """
    provider = os.environ.get("SMS_PROVIDER", "console").strip().lower()
    if provider != "console":
        # Fail-safe deliberado: uma chave apontando para um provedor que ainda
        # não existe NÃO pode virar envio silencioso nem exceção no meio da
        # emissão de uma fatura. Cai no mock e avisa alto.
        logger.warning("SMS_PROVIDER=%r não implementado; usando o transporte de console", provider)
    return ConsoleSmsTransport()


async def send_sms(
    *, to: str, body: str, enabled: bool, transport: SmsTransport | None = None
) -> bool:
    """Envia, se estiver ligado. Devolve `True` se de fato tentou enviar.

    Best-effort por desenho: qualquer falha é registrada e engolida. Quem chama
    é a emissão de fatura, e uma fatura não pode deixar de ser emitida porque
    um SMS falhou.
    """
    if not enabled:
        return False
    if not (to or "").strip():
        logger.warning("sms: aviso ligado mas sem telefone cadastrado — nada enviado")
        return False
    try:
        await (transport or _transport()).send(to=to, body=body)
    except Exception as exc:
        logger.warning("sms: falha ao enviar para %s: %s", mask_phone(to), exc)
        return False
    return True
