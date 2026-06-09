"""Spec #0: tempo/ticket no Znuny SÓ via GI; sem SQL direto no schema znuny."""

from __future__ import annotations

import pathlib

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "gerti_sidecar"
_FILES = [
    _SRC / "domain" / "timer_service.py",
    _SRC / "routers" / "admin_timer.py",
]
_FORBIDDEN = (
    '"public.',
    "'public.",
    '"znuny.',
    "'znuny.",
    "from time_accounting",
    "into time_accounting",
)


def test_no_direct_znuny_schema_access():
    for f in _FILES:
        text = f.read_text(encoding="utf-8").lower()
        for needle in _FORBIDDEN:
            assert needle.lower() not in text, f"{f.name} acessa schema znuny direto: {needle}"
