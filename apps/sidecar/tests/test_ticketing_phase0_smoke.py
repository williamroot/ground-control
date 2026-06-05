"""Fase 0: o cliente GI de ticket existe com as assinaturas congeladas."""

from __future__ import annotations

import inspect

from gerti_sidecar.integrations import znuny_ticket


def test_signatures_frozen():
    for name in ("create_ticket", "search_tickets", "get_ticket", "reply_ticket", "form_meta"):
        assert hasattr(znuny_ticket, name), f"falta {name}"
    # reusa as MESMAS exceções do cliente admin (não cria novas hierarquias)
    from gerti_sidecar.integrations.znuny_customer_admin import (
        ZnunyUnavailable,
        ZnunyWriteError,
    )

    assert znuny_ticket.ZnunyUnavailable is ZnunyUnavailable
    assert znuny_ticket.ZnunyWriteError is ZnunyWriteError
    # create_ticket é async
    assert inspect.iscoroutinefunction(znuny_ticket.create_ticket)
