"""T-R12.3 / S1 — o teto de níveis do catálogo, e a chave que o desliga.

**Esta é a suposição de maior risco da campanha.** O Kleber descreveu o limite
de dois níveis *do TIFLUX* (09:20) — pode ter sido a descrição de uma limitação
que ele tolera, não um requisito dele. Impor um teto que ninguém pediu vira
dívida cara; não impor deixa o catálogo virar árvore de cinco níveis.

A saída foi construir o teto **atrás de `ZNUNY_SERVICE_MAX_DEPTH`**, e testar
nos dois estados: com teto e sem. Reverter é uma variável de ambiente.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from gerti_sidecar.config import get_settings
from gerti_sidecar.routers.admin_znuny import check_service_depth, service_depth


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Suporte", 1),
        ("Suporte::Rede", 2),
        ("Suporte::Rede::VPN", 3),
        ("Suporte::Rede::VPN::Cliente", 4),
        ("", 0),
    ],
)
def test_service_depth_counts_levels(name, expected):
    assert service_depth(name) == expected


def _with_depth(monkeypatch, value: str):
    monkeypatch.setenv("ZNUNY_SERVICE_MAX_DEPTH", value)
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()


def test_two_levels_pass_and_three_are_refused(monkeypatch):
    """Estado padrão: o teto vale."""
    _with_depth(monkeypatch, "2")
    check_service_depth({"Name": "Suporte"})
    check_service_depth({"Name": "Suporte::Rede"})
    with pytest.raises(HTTPException) as exc:
        check_service_depth({"Name": "Suporte::Rede::VPN"})
    assert exc.value.status_code == 422
    # A mensagem precisa DIZER o que houve — se o teto estiver errado, o
    # operador tem que entender por que foi barrado para poder reclamar.
    assert "2 níveis" in exc.value.detail
    assert "Suporte::Rede::VPN" in exc.value.detail


def test_the_cap_can_be_turned_off_entirely(monkeypatch):
    """O outro estado da suposição: `0` = sem teto, e nada é recusado."""
    _with_depth(monkeypatch, "0")
    check_service_depth({"Name": "A::B::C::D::E"})


def test_the_cap_can_be_raised(monkeypatch):
    """E o meio-termo: se ele quiser três níveis, é uma variável."""
    _with_depth(monkeypatch, "3")
    check_service_depth({"Name": "Suporte::Rede::VPN"})
    with pytest.raises(HTTPException):
        check_service_depth({"Name": "Suporte::Rede::VPN::Extra"})


def test_empty_name_is_not_the_depth_check_problem(monkeypatch):
    """Nome vazio é validação do Znuny, não do teto — não invente erro aqui."""
    _with_depth(monkeypatch, "2")
    check_service_depth({"Name": ""})
    check_service_depth({})
