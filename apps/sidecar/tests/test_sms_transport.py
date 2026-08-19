"""T-R6.4 / I-5 — SMS com transporte trocável, e o cuidado com o custo.

O provedor real ainda não existe (Twilio é o candidato). O SMS foi construído
inteiro, com o envio atrás de uma interface e um mock de console como primeiro
transporte.

**SMS tem custo por mensagem**, e o mock esconde isso: é fácil deixar um laço
mandando mil mensagens e só descobrir com o provedor ligado. Os três testes
abaixo são a proteção contra exatamente isso.
"""

from __future__ import annotations

import pytest

from gerti_sidecar.integrations.sms import (
    ConsoleSmsTransport,
    console_log_line,
    mask_phone,
    send_sms,
)


@pytest.mark.parametrize(
    ("phone", "expected"),
    [
        ("+5531999990000", "+55319****0000"),
        ("11999998888", "119999****8888"),
        ("1234", "****"),
        ("", ""),
    ],
)
def test_mask_phone_never_logs_the_whole_number(phone, expected):
    """Telefone inteiro em log de container é dado pessoal vazando."""
    masked = mask_phone(phone)
    assert masked == expected
    if len(phone) > 8:
        assert phone not in masked


@pytest.mark.asyncio
async def test_disabled_means_zero_sends():
    """A proteção que importa: chave desligada NÃO manda, e não é 'silencioso'."""
    t = ConsoleSmsTransport()
    sent = await send_sms(to="+5531999990000", body="oi", enabled=False, transport=t)
    assert sent is False
    assert t.sent == [], "mandou SMS com a chave desligada — isso custa dinheiro"


@pytest.mark.asyncio
async def test_enabled_sends_exactly_once():
    t = ConsoleSmsTransport()
    assert await send_sms(to="+5531999990000", body="Fatura disponível", enabled=True, transport=t)
    assert len(t.sent) == 1
    assert t.sent[0][1] == "Fatura disponível"


@pytest.mark.asyncio
async def test_enabled_without_a_phone_does_not_send():
    """Aviso ligado sem telefone não pode virar exceção nem envio para o vazio."""
    t = ConsoleSmsTransport()
    assert await send_sms(to="", body="oi", enabled=True, transport=t) is False
    assert t.sent == []


@pytest.mark.asyncio
async def test_a_failing_transport_never_breaks_the_caller():
    """Best-effort: uma fatura não pode deixar de ser emitida porque o SMS caiu."""

    class _Broken:
        async def send(self, *, to: str, body: str) -> None:
            raise RuntimeError("provedor fora do ar")

    assert (
        await send_sms(to="+5531999990000", body="oi", enabled=True, transport=_Broken()) is False
    )


@pytest.mark.asyncio
async def test_console_transport_logs_the_number_masked():
    """O modo simulado registra o envio sem guardar o número inteiro.

    A asserção é sobre a LINHA construída, não sobre o logging: a ordem dos
    testes é aleatória e o logging global nem sempre está ligado quando este
    roda — a versão anterior passava isolada e falhava na suíte, que é pior
    que não existir.
    """
    t = ConsoleSmsTransport()
    await send_sms(
        to="+5531999990000", body="Sua fatura está disponível", enabled=True, transport=t
    )

    line = t.log_lines[0]
    assert "simulado" in line
    assert "+5531999990000" not in line, "o telefone inteiro foi para o log"
    assert "****0000" in line
    assert "Sua fatura" in line


def test_the_log_line_truncates_a_long_message():
    """Mensagem gigante não pode inundar o log do container."""
    line = console_log_line("+5531999990000", "x" * 500)
    assert len(line) < 200
