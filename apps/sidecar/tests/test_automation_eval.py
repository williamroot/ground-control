from __future__ import annotations

from gerti_sidecar.domain.automation_eval import ALLOWED_FIELDS, OPS, evaluate


def test_eval_and_semantics():
    facts = {"priority": "5 very high", "title": "Servidor fora do ar", "age_minutes": 120}
    assert (
        evaluate(
            [
                {"field": "priority", "op": "contains", "value": "high"},
                {"field": "age_minutes", "op": "gt", "value": 60},
            ],
            facts,
        )
        is True
    )
    # campo ausente nos facts → False (fail-safe)
    assert evaluate([{"field": "queue", "op": "eq", "value": "Suporte"}], facts) is False
    # campo não-permitido → False (fail-safe, sem exceção)
    assert evaluate([{"field": "__danger__", "op": "eq", "value": "x"}], facts) is False


def test_empty_conditions_match():
    # AND de zero condições é vacuously True (regra sem condição sempre dispara)
    assert evaluate([], {"priority": "x"}) is True


def test_all_ops():
    f = {"state": "open", "title": "rede caiu", "age_minutes": 30, "priority": "3 normal"}
    assert evaluate([{"field": "state", "op": "eq", "value": "open"}], f) is True
    assert evaluate([{"field": "state", "op": "ne", "value": "closed"}], f) is True
    assert evaluate([{"field": "title", "op": "contains", "value": "rede"}], f) is True
    assert evaluate([{"field": "title", "op": "not_contains", "value": "disco"}], f) is True
    assert evaluate([{"field": "age_minutes", "op": "gt", "value": 10}], f) is True
    assert evaluate([{"field": "age_minutes", "op": "lt", "value": 60}], f) is True
    assert evaluate([{"field": "state", "op": "in", "value": ["open", "new"]}], f) is True
    assert evaluate([{"field": "state", "op": "not_in", "value": ["closed"]}], f) is True


def test_numeric_coercion_safe():
    # age_minutes vem como string do Znuny → coerção segura p/ gt/lt
    f = {"age_minutes": "120"}
    assert evaluate([{"field": "age_minutes", "op": "gt", "value": 60}], f) is True
    # valor não-numérico não explode → False
    f2 = {"age_minutes": "n/a"}
    assert evaluate([{"field": "age_minutes", "op": "gt", "value": 60}], f2) is False


def test_unknown_op_fail_safe():
    assert evaluate([{"field": "state", "op": "regex", "value": ".*"}], {"state": "open"}) is False


def test_malformed_condition_fail_safe():
    # condição sem field/op → False, nunca exceção
    assert evaluate([{"op": "eq", "value": "x"}], {"state": "open"}) is False
    assert evaluate([{"field": "state"}], {"state": "open"}) is False
    assert evaluate(["not a dict"], {"state": "open"}) is False  # type: ignore[list-item]


def test_constants_exported():
    assert "priority" in ALLOWED_FIELDS
    assert "__danger__" not in ALLOWED_FIELDS
    assert "eq" in OPS and "contains" in OPS
