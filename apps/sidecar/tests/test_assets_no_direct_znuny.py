"""Spec #1K Fase 2 Task 5 — grep-guard: assets.py só via GI, sem SQL direto.

Espelha test_consumo_no_direct_znuny.py: garante que routers/assets.py não
contém needles de acesso SQL direto ao schema znuny ou public.
"""

from __future__ import annotations

import pathlib

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "gerti_sidecar"
_FILES = [
    _SRC / "routers" / "assets.py",
]

# SQL direto ao schema znuny ou public (padrões de acesso, não nomes de variável).
_FORBIDDEN = (
    '"public.',
    "'public.",
    '"znuny.',
    "'znuny.",
)


def test_assets_no_direct_znuny_schema_access():
    for f in _FILES:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8").lower()
        for needle in _FORBIDDEN:
            assert (
                needle.lower() not in text
            ), f"{f.name} acessa schema/tabela znuny diretamente: {needle}"
