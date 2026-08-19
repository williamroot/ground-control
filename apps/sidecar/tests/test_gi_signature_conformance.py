"""As chamadas ao Znuny têm de caber na assinatura REAL — não só na do espião.

Este arquivo existe por causa de um defeito que atravessou 793 testes verdes e
só apareceu no staging: `TicketingService` passou a mandar `state=` para
`create_ticket`, e o parâmetro nunca foi acrescentado à função de verdade.
Todo teste de domínio usa um espião com `**kw`, que aceita qualquer coisa —
então o erro era invisível até um chamado ser aberto de verdade
(`TypeError: create_ticket() got an unexpected keyword argument 'state'`).

É a mesma lição da Onda 1 (a guarda de fila que passava no serviço e era
código morto na rota) numa forma nova: **o dublê é mais permissivo que o
original, e é por aí que passa o defeito.**

A checagem é a assinatura, com `inspect`: barata, sem rede, e falha no
instante em que alguém acrescenta um argumento de um lado só.
"""

from __future__ import annotations

import inspect

from gerti_sidecar.integrations import znuny_ticket

# O que cada serviço manda, hoje, para cada função do GI. Acrescentar um
# argumento na chamada sem acrescentá-lo aqui não quebra nada — mas
# acrescentá-lo aqui sem acrescentá-lo na função real quebra, que é o ponto.
_CALLS = {
    "create_ticket": {
        "customer_user",
        "customer_id",
        "title",
        "body",
        "service",
        "type_",
        "priority",
        "contract_id",
        "attachments",
        "config_item_id",
        "queue",
        "state",
    },
    "agent_ticket_update": {"ticket_id", "state", "note"},
}


def _accepted(func) -> set[str]:
    sig = inspect.signature(func)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        raise AssertionError(
            f"{func.__name__} aceita **kwargs — a conformidade de assinatura "
            "deixa de valer e o defeito volta a passar"
        )
    return set(sig.parameters)


def test_every_argument_the_domain_sends_exists_in_the_real_function():
    for name, sent in _CALLS.items():
        func = getattr(znuny_ticket, name)
        accepted = _accepted(func)
        missing = sent - accepted
        assert not missing, (
            f"{name}() não aceita {sorted(missing)} — o domínio manda esses "
            f"argumentos e a chamada real vai explodir em runtime"
        )


def test_the_ticketing_service_call_matches_create_ticket():
    """Amarra o conjunto acima ao código de verdade, e não a uma lista solta.

    Lê os `kwargs` do `create_ticket` dentro de `TicketingService.open_ticket`
    a partir da árvore sintática: se alguém acrescentar um argumento lá e
    esquecer da integração, este teste falha sem ninguém precisar lembrar de
    atualizar `_CALLS`.
    """
    import ast
    import textwrap

    from gerti_sidecar.domain import ticketing_service

    source = textwrap.dedent(inspect.getsource(ticketing_service.TicketingService.open_ticket))
    tree = ast.parse(source)
    sent: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_ticket"
        ):
            sent = {kw.arg for kw in node.keywords if kw.arg}
    assert sent, "não encontrei a chamada a create_ticket — o teste ficou cego"

    missing = sent - _accepted(znuny_ticket.create_ticket)
    assert not missing, f"TicketingService manda {sorted(missing)}, que create_ticket() não aceita"
