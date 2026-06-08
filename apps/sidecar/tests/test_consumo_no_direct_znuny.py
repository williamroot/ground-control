"""Spec #0: leitura de tempo no Znuny SÓ via GI; sem SQL direto no schema znuny.

Os needles testam acesso SQL direto (schema-qualified ou via FROM/JOIN à tabela
nativa), não menções legítimas ao nome da tabela em docstrings/variáveis.
"""

from __future__ import annotations

import pathlib

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "gerti_sidecar"
_FILES = [
    _SRC / "domain" / "reconciliation_service.py",
    _SRC / "domain" / "cycle_closer.py",
    _SRC / "jobs" / "worker.py",
]
# SQL direto ao schema znuny ou à tabela nativa (padrões de acesso, não nomes de variável).
_FORBIDDEN = (
    '"public.',
    "'public.",
    '"znuny.',
    "'znuny.",
    "from time_accounting",
    "join time_accounting",
    "table time_accounting",
    "insert into time_accounting",
    "update time_accounting",
)


def test_no_direct_znuny_schema_access():
    for f in _FILES:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8").lower()
        for needle in _FORBIDDEN:
            assert (
                needle.lower() not in text
            ), f"{f.name} acessa schema/tabela znuny diretamente: {needle}"
