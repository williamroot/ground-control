"""Static guard: the #1F-b read paths NEVER mutate the #1C domain (H3)."""

from __future__ import annotations

from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src" / "gerti_sidecar"
_FILES = [
    _SRC / "domain" / "contract_read_service.py",
    _SRC / "routers" / "dashboard.py",
    _SRC / "routers" / "contracts.py",
]
_FORBIDDEN = (
    ".add(",
    ".add_all(",
    ".flush(",
    ".commit(",
    ".delete(",
    "insert(",
    "update(",
    ".record(",
    ".close(",
    ".apply_adjustment(",
    ".renew(",
)


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_no_mutation_tokens(path):
    text = path.read_text()
    hits = [tok for tok in _FORBIDDEN if tok in text]
    assert hits == [], f"{path.name} contains mutation token(s): {hits}"
