"""V-R11.2 — o cálculo da próxima ocorrência (T-R11.2).

Função pura, então dá para testar exaustivamente. O caso que quebra
implementações ingênuas — e o motivo de este arquivo existir — é **"todo dia
31"**: fevereiro não tem. Pular o mês faria a tarefa sumir sem avisar; estourar
para o dia 1º jogaria a manutenção de fechamento no mês errado. Grudamos no
último dia do mês, que é o que um humano entende por "todo fim de mês".
"""

from __future__ import annotations

import datetime as dt

import pytest

from gerti_sidecar.domain.recurrence import (
    clamp_day_of_month,
    describe,
    next_occurrence,
    occurrences_between,
)

D = dt.date


# ── o caso do dia 31 ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("year", "month", "day", "expected"),
    [
        (2026, 2, 31, D(2026, 2, 28)),  # fevereiro comum
        (2024, 2, 31, D(2024, 2, 29)),  # bissexto
        (2026, 4, 31, D(2026, 4, 30)),  # abril tem 30
        (2026, 1, 31, D(2026, 1, 31)),  # janeiro tem, não mexe
        (2026, 2, 15, D(2026, 2, 15)),  # dia normal, não mexe
    ],
)
def test_clamp_day_of_month(year, month, day, expected):
    assert clamp_day_of_month(year, month, day) == expected


def test_monthly_on_the_31st_lands_on_the_last_day_of_february():
    """O aceite do T-R11.2, escrito como o requisito o descreve."""
    nxt = next_occurrence(
        frequency="monthly", starts_on=D(2026, 1, 1), day_of_month=31, after=D(2026, 2, 1)
    )
    assert nxt == D(2026, 2, 28)


# ── semanal ─────────────────────────────────────────────────────────────────


def test_weekly_finds_the_next_matching_weekday():
    # 2026-08-19 é uma quarta-feira (weekday 2).
    assert D(2026, 8, 19).weekday() == 2
    # Próxima segunda (0) a partir de quarta é 24/08.
    assert next_occurrence(
        frequency="weekly", starts_on=D(2026, 1, 1), weekday=0, after=D(2026, 8, 19)
    ) == D(2026, 8, 24)
    # Se HOJE já é o dia certo, é hoje — não a semana que vem.
    assert next_occurrence(
        frequency="weekly", starts_on=D(2026, 1, 1), weekday=2, after=D(2026, 8, 19)
    ) == D(2026, 8, 19)


def test_weekly_without_a_weekday_has_no_next_occurrence():
    """Forma inválida não pode virar data chutada — o banco também recusa."""
    assert (
        next_occurrence(frequency="weekly", starts_on=D(2026, 1, 1), after=D(2026, 8, 19)) is None
    )


# ── janelas e limites ───────────────────────────────────────────────────────


def test_never_returns_a_date_before_starts_on():
    assert next_occurrence(
        frequency="weekly", starts_on=D(2026, 9, 1), weekday=0, after=D(2026, 8, 1)
    ) == D(2026, 9, 7)


def test_respects_ends_on():
    assert (
        next_occurrence(
            frequency="monthly",
            starts_on=D(2026, 1, 1),
            ends_on=D(2026, 6, 30),
            day_of_month=15,
            after=D(2026, 7, 1),
        )
        is None
    )


def test_once_happens_once_and_then_never():
    assert next_occurrence(frequency="once", starts_on=D(2026, 9, 10), after=D(2026, 8, 1)) == D(
        2026, 9, 10
    )
    # Passou: acabou.
    assert next_occurrence(frequency="once", starts_on=D(2026, 7, 10), after=D(2026, 8, 1)) is None


def test_month_rollover_including_december():
    assert next_occurrence(
        frequency="monthly", starts_on=D(2026, 1, 1), day_of_month=5, after=D(2026, 12, 10)
    ) == D(2027, 1, 5)


# ── agenda dos próximos 30 dias (T-R11.5) ───────────────────────────────────


def test_occurrences_between_lists_the_agenda():
    got = occurrences_between(
        frequency="weekly",
        starts_on=D(2026, 1, 1),
        ends_on=None,
        weekday=0,  # segundas
        day_of_month=None,
        since=D(2026, 8, 19),
        until=D(2026, 9, 18),
    )
    assert got == [D(2026, 8, 24), D(2026, 8, 31), D(2026, 9, 7), D(2026, 9, 14)]
    assert all(d.weekday() == 0 for d in got)


def test_occurrences_between_is_bounded():
    """Janela absurda não pode virar laço infinito nem lista gigante numa tela."""
    got = occurrences_between(
        frequency="weekly",
        starts_on=D(2020, 1, 1),
        ends_on=None,
        weekday=0,
        day_of_month=None,
        since=D(2020, 1, 1),
        until=D(2030, 1, 1),
        limit=10,
    )
    assert len(got) == 10


def test_once_appears_at_most_once_in_the_agenda():
    got = occurrences_between(
        frequency="once",
        starts_on=D(2026, 8, 25),
        ends_on=None,
        weekday=None,
        day_of_month=None,
        since=D(2026, 8, 19),
        until=D(2026, 9, 18),
    )
    assert got == [D(2026, 8, 25)]


# ── rótulo ──────────────────────────────────────────────────────────────────


def test_describe_reads_like_the_video():
    assert (
        describe(frequency="weekly", weekday=0, day_of_month=None, at_time=dt.time(8, 0))
        == "toda segunda-feira, 08:00"
    )
    assert (
        describe(frequency="monthly", weekday=None, day_of_month=5, at_time=dt.time(9, 30))
        == "todo dia 5, 09:30"
    )


def test_describe_warns_about_short_months():
    """Se o operador escolheu dia 31, a tela precisa dizer o que acontece."""
    label = describe(frequency="monthly", weekday=None, day_of_month=31, at_time=dt.time(8, 0))
    assert "último dia" in label
