"""D-R — teto e validade do saldo acumulado.

Módulo puro, então os testes são a especificação executável da regra de
dinheiro. O caso que justifica a existência dos baldes é
`test_expiry_is_impossible_with_a_single_number`.
"""

from __future__ import annotations

import datetime as dt

from gerti_sidecar.domain.carry_over import (
    Bucket,
    apply_cap,
    buckets_from_cycle_totals,
    consume_fifo,
    drop_expired,
    roll,
    total,
)

D = dt.date


def _b(amount, y, m, d):
    return Bucket(amount, D(y, m, d))


# ── validade ────────────────────────────────────────────────────────────────


def test_no_expiry_is_the_default():
    """Contrato sem prazo configurado mantém o comportamento de antes da Onda 5."""
    old = [_b(600, 2020, 1, 31)]
    assert drop_expired(old, on=D(2026, 1, 1), expires_days=None) == old
    assert drop_expired(old, on=D(2026, 1, 1), expires_days=0) == old


def test_expiry_drops_only_what_is_past_the_deadline():
    buckets = [_b(60, 2026, 1, 31), _b(120, 2026, 3, 31)]
    # 60 dias após 31/01 = 01/04; o ciclo começa em 01/05 → aquele venceu.
    alive = drop_expired(buckets, on=D(2026, 5, 1), expires_days=60)
    assert [b.amount for b in alive] == [120]


def test_expiry_is_inclusive_on_the_last_day():
    """Vencer no dia é ainda estar válido — a dúvida cai a favor do cliente."""
    buckets = [_b(60, 2026, 1, 1)]
    assert drop_expired(buckets, on=D(2026, 1, 31), expires_days=30) == buckets
    assert drop_expired(buckets, on=D(2026, 2, 1), expires_days=30) == []


def test_expiry_is_impossible_with_a_single_number():
    """O caso que obrigou os baldes.

    Saldo gerado em jan/2026, com validade de 60 dias, atravessando ciclos
    mensais em que nada é consumido. Com um número só, cada fechamento
    reescreveria o saldo com a data do fechamento e ele nunca venceria. Com
    baldes, a data de origem sobrevive à cadeia e o saldo morre em abril.
    """
    buckets = [_b(600, 2026, 1, 31)]
    for month in (2, 3):  # fev, mar: nada consumido, nada de franquia nova
        r = roll(
            previous=buckets,
            consumed=0.0,
            base_franchise=0.0,
            period_start=D(2026, month, 1),
            period_end=D(2026, month, 28),
            accumulate=True,
            cap=None,
            expires_days=60,
        )
        buckets = r.buckets_out
        assert total(buckets) == 600, "o saldo sumiu antes de vencer"
        assert buckets[0].earned_on == D(2026, 1, 31), "a data de origem foi reescrita"

    # Abril: 60 dias após 31/01 já passaram.
    r = roll(
        previous=buckets,
        consumed=0.0,
        base_franchise=0.0,
        period_start=D(2026, 4, 15),
        period_end=D(2026, 4, 30),
        accumulate=True,
        cap=None,
        expires_days=60,
    )
    assert r.carry_in == 0.0
    assert r.expired == 600


# ── teto ────────────────────────────────────────────────────────────────────


def test_cap_keeps_the_newest_balance():
    """Cortado pelo teto, sobrevive o saldo de maior vida útil restante."""
    kept = apply_cap([_b(300, 2026, 1, 31), _b(300, 2026, 2, 28)], cap=400)
    assert total(kept) == 400
    # 300 do mais novo, inteiro, + 100 do mais velho.
    assert {(b.amount, b.earned_on) for b in kept} == {
        (300.0, D(2026, 2, 28)),
        (100.0, D(2026, 1, 31)),
    }


def test_cap_of_zero_means_no_accumulation():
    assert apply_cap([_b(300, 2026, 1, 31)], cap=0) == []


def test_no_cap_is_the_default():
    b = [_b(9999, 2026, 1, 31)]
    assert apply_cap(b, cap=None) == b


def test_cap_reports_what_was_discarded():
    """O cliente vai perguntar para onde foram as horas; o snapshot responde."""
    r = roll(
        previous=[_b(600, 2026, 1, 31)],
        consumed=0.0,
        base_franchise=0.0,
        period_start=D(2026, 2, 1),
        period_end=D(2026, 2, 28),
        accumulate=True,
        cap=200,
        expires_days=None,
    )
    assert r.carry_in == 200
    assert r.capped == 400


# ── consumo FIFO ────────────────────────────────────────────────────────────


def test_consumption_spends_the_oldest_first():
    left = consume_fifo([_b(100, 2026, 1, 31), _b(100, 2026, 2, 28)], 150)
    assert [(b.amount, b.earned_on) for b in left] == [(50.0, D(2026, 2, 28))]


def test_consuming_more_than_the_balance_just_zeroes_it():
    assert consume_fifo([_b(100, 2026, 1, 31)], 500) == []


def test_the_month_franchise_is_spent_after_the_carried_balance():
    """FIFO de verdade: gasta o que vence antes, não o que chegou por último."""
    r = roll(
        previous=[_b(600, 2026, 1, 31)],  # 10 h acumuladas
        consumed=900.0,  # 15 h consumidas
        base_franchise=1200.0,  # 20 h de franquia do mês
        period_start=D(2026, 2, 1),
        period_end=D(2026, 2, 28),
        accumulate=True,
        cap=None,
        expires_days=None,
    )
    # As 15 h saíram das 10 h velhas + 5 h da franquia. Sobram 15 h da
    # franquia do mês, datadas em fevereiro — e nada do saldo velho.
    assert r.carry_out == 900.0
    assert [(b.amount, b.earned_on) for b in r.buckets_out] == [(900.0, D(2026, 2, 28))]


def test_leftover_old_balance_keeps_its_original_date():
    """Não usar o saldo não pode renovar o prazo dele."""
    r = roll(
        previous=[_b(600, 2026, 1, 31)],
        consumed=120.0,
        base_franchise=1200.0,
        period_start=D(2026, 2, 1),
        period_end=D(2026, 2, 28),
        accumulate=True,
        cap=None,
        expires_days=None,
    )
    dates = {b.earned_on for b in r.buckets_out}
    assert D(2026, 1, 31) in dates, "a data de origem do saldo restante foi renovada"
    assert r.carry_out == 480 + 1200


# ── contratos que não acumulam ──────────────────────────────────────────────


def test_not_accumulating_carries_nothing_forward():
    r = roll(
        previous=[],
        consumed=0.0,
        base_franchise=1200.0,
        period_start=D(2026, 2, 1),
        period_end=D(2026, 2, 28),
        accumulate=False,
        cap=None,
        expires_days=None,
    )
    assert r.carry_out == 0.0
    assert r.buckets_out == []


# ── compatibilidade com ciclos fechados antes da Onda 5 ─────────────────────


def test_a_pre_onda5_cycle_keeps_its_balance():
    """Ligar a validade não pode apagar o saldo histórico de todo mundo."""
    buckets = buckets_from_cycle_totals(
        {"carry_over": 480.0}, legacy_key="carry_over", fallback_date=D(2026, 1, 31)
    )
    assert [(b.amount, b.earned_on) for b in buckets] == [(480.0, D(2026, 1, 31))]


def test_buckets_win_over_the_legacy_number():
    buckets = buckets_from_cycle_totals(
        {
            "carry_over": 999.0,
            "carry_buckets": [{"amount": 60.0, "earned_on": "2026-02-28"}],
        },
        legacy_key="carry_over",
        fallback_date=D(2026, 1, 31),
    )
    assert [(b.amount, b.earned_on) for b in buckets] == [(60.0, D(2026, 2, 28))]


def test_garbage_in_totals_never_raises():
    """`totals` é JSONB — assumir formato aqui derruba o fechamento do ciclo."""
    for raw in (None, {}, {"carry_buckets": "nao é lista"}, {"carry_buckets": [1, "x", {}]}):
        assert (
            buckets_from_cycle_totals(raw, legacy_key="carry_over", fallback_date=D(2026, 1, 1))
            == []
        )
