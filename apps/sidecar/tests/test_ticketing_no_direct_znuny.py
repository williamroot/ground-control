# apps/sidecar/tests/test_ticketing_no_direct_znuny.py
"""Spec #0: escrita/leitura de ticket SÓ via GI. Nenhum SQL direto no schema
znuny/public a partir dos módulos de ticketing."""

from __future__ import annotations

import pathlib

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "gerti_sidecar"
_FILES = [
    _SRC / "routers" / "tickets.py",
    _SRC / "routers" / "ticketing_meta.py",
    _SRC / "domain" / "ticketing_service.py",
]
_FORBIDDEN = ('"public.', "'public.", '"znuny.', "'znuny.", '"customer_user"', '"customer_company"')


def test_no_direct_znuny_schema_access():
    for f in _FILES:
        text = f.read_text(encoding="utf-8").lower()
        for needle in _FORBIDDEN:
            assert (
                needle.lower() not in text
            ), f"{f.name} referencia schema znuny diretamente: {needle}"
