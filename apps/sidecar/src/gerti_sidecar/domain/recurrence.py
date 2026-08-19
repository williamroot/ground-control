"""Cálculo da próxima ocorrência de uma tarefa recorrente (T-R11.2, R11).

Função **pura**: sem banco, sem relógio implícito, sem I/O. Isso é deliberado —
é a parte da agenda que mais dá errado em silêncio, e uma função pura é a que
dá para testar exaustivamente sem subir nada.

O caso que quebra implementações ingênuas: **"todo dia 31"**. Fevereiro não tem
dia 31, abril também não. As opções eram pular o mês (a tarefa some sem
avisar), estourar para o dia 1º do mês seguinte (a manutenção do fechamento
cairia no mês errado), ou **grudar no último dia do mês**. Escolhemos a
terceira: "todo dia 31" em fevereiro é 28 — ou 29 em ano bissexto. É o que um
humano entende por "todo fim de mês", e é o que a tela promete.
"""

from __future__ import annotations

import calendar
import datetime as dt

FREQUENCY_LABELS = {
    "once": "uma vez",
    "weekly": "toda semana",
    "monthly": "todo mês",
}

WEEKDAY_LABELS = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
]


def clamp_day_of_month(year: int, month: int, day: int) -> dt.date:
    """Dia do mês que existe de verdade — 31 em fevereiro vira 28 (ou 29).

    Ver o cabeçalho do módulo: grudar no último dia é a leitura que bate com
    "todo fim de mês", e é a única das três opções que nunca faz a tarefa
    sumir nem cair no mês errado.
    """
    last = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(day, last))


def next_occurrence(
    *,
    frequency: str,
    starts_on: dt.date,
    ends_on: dt.date | None = None,
    weekday: int | None = None,
    day_of_month: int | None = None,
    after: dt.date,
) -> dt.date | None:
    """Primeira ocorrência **em ou depois de** `after`. `None` = acabou.

    `after` é sempre explícito: uma agenda que consulta o relógio por conta
    própria é impossível de testar e imprevisível num worker que pode atrasar.

    Nunca devolve data anterior a `starts_on`, nem posterior a `ends_on`.
    """
    if frequency not in ("once", "weekly", "monthly"):
        return None

    floor = max(after, starts_on)

    if frequency == "once":
        candidate: dt.date | None = starts_on if starts_on >= after else None
    elif frequency == "weekly":
        if weekday is None:
            return None
        # `weekday()` do Python já é 0=segunda … 6=domingo, igual ao nosso.
        delta = (weekday - floor.weekday()) % 7
        candidate = floor + dt.timedelta(days=delta)
    else:  # monthly
        if day_of_month is None:
            return None
        candidate = clamp_day_of_month(floor.year, floor.month, day_of_month)
        if candidate < floor:
            # Já passou neste mês: vai para o próximo, virando o ano se preciso.
            year = floor.year + (1 if floor.month == 12 else 0)
            month = 1 if floor.month == 12 else floor.month + 1
            candidate = clamp_day_of_month(year, month, day_of_month)

    if candidate is None:
        return None
    if ends_on is not None and candidate > ends_on:
        return None
    return candidate


def occurrences_between(
    *,
    frequency: str,
    starts_on: dt.date,
    ends_on: dt.date | None,
    weekday: int | None,
    day_of_month: int | None,
    since: dt.date,
    until: dt.date,
    limit: int = 60,
) -> list[dt.date]:
    """Todas as ocorrências na janela — alimenta a agenda de 30 dias (T-R11.5).

    `limit` é rede de segurança, não regra de negócio: uma janela absurda não
    pode virar laço infinito nem lista de milhares de datas numa tela.
    """
    out: list[dt.date] = []
    cursor = since
    while len(out) < limit:
        nxt = next_occurrence(
            frequency=frequency,
            starts_on=starts_on,
            ends_on=ends_on,
            weekday=weekday,
            day_of_month=day_of_month,
            after=cursor,
        )
        if nxt is None or nxt > until:
            break
        out.append(nxt)
        cursor = nxt + dt.timedelta(days=1)
        if frequency == "once":
            break
    return out


def describe(
    *, frequency: str, weekday: int | None, day_of_month: int | None, at_time: dt.time
) -> str:
    """ "toda segunda-feira, 08:00" — o rótulo que a tela mostra.

    Fica aqui, e não no template, porque é a mesma frase que precisa aparecer
    na lista, no relatório e na confirmação — três lugares que não podem
    divergir.
    """
    hhmm = at_time.strftime("%H:%M")
    if frequency == "weekly" and weekday is not None:
        return f"toda {WEEKDAY_LABELS[weekday]}, {hhmm}"
    if frequency == "monthly" and day_of_month is not None:
        suffix = " (ou no último dia, em meses mais curtos)" if day_of_month > 28 else ""
        return f"todo dia {day_of_month}, {hhmm}{suffix}"
    return f"uma vez, {hhmm}"
