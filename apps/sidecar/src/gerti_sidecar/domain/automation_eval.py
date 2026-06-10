"""Avaliador de condições puro para o motor de automação (Spec #1Q, Task 2).

DSL `{field, op, value}`. `evaluate(conditions, facts)` é o AND de todas as
condições. **Fonte única de verdade** das allowlists (`ALLOWED_FIELDS`, `OPS`)
reusada pela validação server-side do CRUD (Task 5) e pelos metadados da UI.

Garantias de segurança (roadmap §E):
- NENHUM `eval`/`exec`/`getattr` dinâmico. `OPS` é um dict de funções puras.
- Campo fora da allowlist → `False` (fail-safe, NUNCA exceção).
- Campo ausente nos facts → `False`.
- Op desconhecida → `False`. Condição malformada → `False`.
- Coerção numérica só para `gt`/`lt` (e o campo numérico `age_minutes`), com
  try/except → `False` se não coercível.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

# Campos que uma condição pode referenciar (espelha os facts montados pelo
# Event module do Znuny + idade calculada). Qualquer outro → fail-safe False.
ALLOWED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "priority",
        "queue",
        "state",
        "type",
        "service",
        "customer_id",
        "title",
        "age_minutes",
        "sla_state",
    }
)


def _to_number(value: Any) -> float:
    # Levanta em valor não-numérico; o caller captura e retorna False.
    if isinstance(value, bool):  # bool é subclasse de int — rejeita explicitamente
        raise ValueError("bool não é número válido")
    return float(value)


def _op_eq(fact: Any, value: Any) -> bool:
    return str(fact) == str(value)


def _op_ne(fact: Any, value: Any) -> bool:
    return str(fact) != str(value)


def _op_contains(fact: Any, value: Any) -> bool:
    return str(value).lower() in str(fact).lower()


def _op_not_contains(fact: Any, value: Any) -> bool:
    return str(value).lower() not in str(fact).lower()


def _op_gt(fact: Any, value: Any) -> bool:
    return _to_number(fact) > _to_number(value)


def _op_lt(fact: Any, value: Any) -> bool:
    return _to_number(fact) < _to_number(value)


def _op_in(fact: Any, value: Any) -> bool:
    if not isinstance(value, (list | tuple | set)):
        return False
    return str(fact) in {str(v) for v in value}


def _op_not_in(fact: Any, value: Any) -> bool:
    if not isinstance(value, (list | tuple | set)):
        return False
    return str(fact) not in {str(v) for v in value}


OPS: Final[dict[str, Callable[[Any, Any], bool]]] = {
    "eq": _op_eq,
    "ne": _op_ne,
    "contains": _op_contains,
    "not_contains": _op_not_contains,
    "gt": _op_gt,
    "lt": _op_lt,
    "in": _op_in,
    "not_in": _op_not_in,
}


def _test(condition: Any, facts: dict[str, Any]) -> bool:
    if not isinstance(condition, dict):
        return False
    field = condition.get("field")
    op = condition.get("op")
    value = condition.get("value")
    # allowlist de campo e de operador — fail-safe.
    if field not in ALLOWED_FIELDS:
        return False
    if op not in OPS:
        return False
    if field not in facts:
        return False
    fn = OPS[op]
    try:
        return bool(fn(facts[field], value))
    except (ValueError, TypeError):
        return False


def evaluate(conditions: Any, facts: dict[str, Any]) -> bool:
    """AND de todas as condições. Lista vazia → True (regra sem condição dispara)."""
    if not isinstance(conditions, (list | tuple)):
        return False
    return all(_test(c, facts) for c in conditions)
