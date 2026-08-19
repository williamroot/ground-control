"""As chaves que a documentação promete como reversíveis TÊM de chegar ao container.

A disciplina de suposições desta campanha se apoia numa promessa repetida em
todo documento: *"se ele discordar, é uma variável de ambiente e recriar o
sidecar"*. Essa promessa é **falsa** se a variável não estiver declarada no
`docker-compose.yml`, porque o bloco `environment:` lista cada uma a uma — o
que não está lá não chega ao processo, e o `Settings` cai no default para
sempre.

Foi o que a verificação ao vivo da Onda 6 encontrou: **quatro** chaves
documentadas como reversíveis estavam ausentes, incluindo
`ZNUNY_SERVICE_MAX_DEPTH`, que é a suposição de maior risco da campanha
inteira. Ninguém teria descoberto até alguém tentar mudar de ideia e o sistema
ignorar em silêncio.
"""

from __future__ import annotations

import pathlib

import pytest

from gerti_sidecar.config import Settings

_COMPOSE = pathlib.Path(__file__).resolve().parents[3] / "docker-compose.yml"

# Chaves que algum documento promete que dá para virar sem tocar em código.
# Acrescentar uma suposição atrás de chave? Acrescente aqui também.
DOCUMENTED_SWITCHES = (
    "ZNUNY_SERVICE_MAX_DEPTH",  # S1, Onda 4 — teto do catálogo de serviço
    "REPORT_TOP_DIMENSION",  # S2, Onda 3 — "principais tipos de chamado"
    "CONSUMPTION_WINDOW_MODE",  # S3, Onda 3 — "últimos três meses"
    "CONSUMPTION_WINDOW_COUNT",  # S3, Onda 3
    "LICENSE_ENFORCEMENT_ENABLED",  # A6.1, Onda 6 — o gate de módulos
    "AI_FEATURES_ENABLED",  # kill-switch da IA
    "ASAAS_ENABLED",  # kill-switch do checkout/cobrança
)


@pytest.mark.parametrize("key", DOCUMENTED_SWITCHES)
def test_the_switch_is_declared_in_compose(key: str):
    """Sem esta linha no compose, a chave nunca chega ao processo."""
    if not _COMPOSE.exists():  # pragma: no cover - checkout parcial
        pytest.skip("docker-compose.yml fora do checkout")
    assert key in _COMPOSE.read_text(), (
        f"{key} é documentada como reversível por ambiente, mas não está no "
        "bloco `environment:` do docker-compose.yml — mudá-la no .env.prod não "
        "teria efeito nenhum"
    )


@pytest.mark.parametrize("key", DOCUMENTED_SWITCHES)
def test_the_switch_exists_in_settings(key: str):
    """O outro lado: chave no compose que o Settings não lê é igualmente muda."""
    assert (
        key.lower() in Settings.model_fields
    ), f"{key} está prometida como chave, mas não existe em Settings"
