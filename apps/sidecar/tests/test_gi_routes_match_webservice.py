"""Todo caminho GI usado pelos clientes existe como rota no webservice.

Por que este teste existe: o `perl -c` do build garante que a operação **compila**,
e o teste de router garante que o sidecar **chama** o cliente — mas nada ligava o
caminho HTTP do cliente Python à `RouteOperationMapping` do YAML. O resultado foi
um 500 do Znuny em produção (`Error while determine Operation for request URI
'/AdminCiClass/List'`) com quatro caminhos divergentes que passaram por todos os
gates: `/AdminObject` (era `/AdminObject/Add`) e os três de `CiClass`.

É um erro barato de cometer e caro de achar — só aparece exercitando contra um
Znuny vivo. Este teste fecha a lacuna lendo as duas fontes e comparando.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
INTEGRATIONS = ROOT / "apps" / "sidecar" / "src" / "gerti_sidecar" / "integrations"

# (arquivo do cliente, webservice que ele consome)
CLIENTS = [
    ("znuny_admin_objects.py", "GertiAdmin"),
    ("znuny_admin_people.py", "GertiAdmin"),
    ("znuny_admin_sysconfig.py", "GertiAdmin"),
]


def _routes_of(webservice: str) -> set[str]:
    """Caminhos declarados em RouteOperationMapping do webservice."""
    spec = yaml.safe_load((ROOT / "znuny" / "webservices" / f"{webservice}.yml").read_text())
    mapping = spec["Provider"]["Transport"]["Config"]["RouteOperationMapping"]
    return {entry["Route"] for entry in mapping.values()}


def _paths_used_by(client_file: str) -> set[str]:
    """Caminhos passados como 1º argumento de `_post(...)` no cliente."""
    source = (INTEGRATIONS / client_file).read_text()
    return set(re.findall(r'_post\(\s*"(/[A-Za-z0-9/_-]+)"', source))


@pytest.mark.parametrize(("client_file", "webservice"), CLIENTS)
def test_every_client_path_is_a_declared_route(client_file: str, webservice: str) -> None:
    used = _paths_used_by(client_file)
    assert used, f"nenhum caminho encontrado em {client_file} — regex do teste desatualizado?"

    declared = _routes_of(webservice)
    unknown = sorted(used - declared)
    assert not unknown, (
        f"{client_file} chama caminho(s) que o webservice {webservice} não roteia: {unknown}. "
        f"O Znuny responderia 500 'Error while determine Operation for request URI'. "
        f"Rotas declaradas: {sorted(declared)}"
    )


def test_every_declared_operation_has_a_route() -> None:
    """Operação sem rota é inalcançável — o outro lado do mesmo erro."""
    spec = yaml.safe_load((ROOT / "znuny" / "webservices" / "GertiAdmin.yml").read_text())
    provider = spec["Provider"]
    operations = set(provider["Operation"].keys())
    routed = set(provider["Transport"]["Config"]["RouteOperationMapping"].keys())

    unreachable = sorted(operations - routed)
    assert not unreachable, f"operações declaradas mas sem rota (inalcançáveis): {unreachable}"

    orphan = sorted(routed - operations)
    assert not orphan, f"rotas apontando para operação inexistente: {orphan}"
