"""Saldo acumulado entre ciclos, com teto e validade (decisão **D-R**, Onda 5).

Até a Onda 4 o acúmulo era um número só: `carry_over`, sem teto e sem prazo.
A Onda 0 registrou a dúvida e ela ficou aberta porque não havia como responder
sem inventar a regra de negócio.

**Por que um número só não serve.** O acúmulo é em cadeia — o saldo do ciclo N
já embute o de N-1 —, então o número perde a data de origem. Sem data de
origem, "o saldo vale 60 dias" não tem como ser aplicado: todo saldo pareceria
ter nascido no último fechamento e nunca expiraria. Validade exige saber
**quando cada pedaço do saldo foi gerado**, e é por isso que aqui o saldo é uma
lista de baldes `(quantidade, gerado_em)`.

Duas escolhas dentro da regra, ambas na direção do cliente:

* **Consumo é FIFO** — gasta primeiro o saldo mais antigo, o que está mais
  perto de vencer. O contrário (gastar o novo primeiro) faria o cliente perder
  saldo por expiração tendo saldo em caixa.
* **Quando o teto corta, sobrevive o mais NOVO.** Se o cliente só pode carregar
  40 h e tem 50 h, as 10 h descartadas são as mais antigas — as que restam são
  as de maior vida útil.

`cap=None` / `expires_days=None` significam **ilimitado**, que é o
comportamento de antes desta onda e segue sendo o padrão de todo contrato.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Bucket:
    """Um pedaço de saldo acumulado e a data em que foi gerado."""

    amount: float
    earned_on: dt.date

    def to_json(self) -> dict[str, Any]:
        return {"amount": round(self.amount, 4), "earned_on": self.earned_on.isoformat()}


def buckets_from_json(raw: Any) -> list[Bucket]:
    """Lê os baldes de `cycle.totals`, tolerando ciclo fechado por versão antiga.

    Um ciclo anterior à Onda 5 tem `carry_over` (número) e nenhum balde. Nesse
    caso o saldo existe e não pode ser descartado — ele vira um balde único, e
    a data de origem é a única defensável: quem chama passa o fim daquele
    ciclo. Ver `buckets_from_cycle_totals`.
    """
    if not isinstance(raw, list):
        return []
    out: list[Bucket] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        amount = item.get("amount")
        earned = item.get("earned_on")
        if not isinstance(amount, int | float) or not isinstance(earned, str):
            continue
        try:
            day = dt.date.fromisoformat(earned)
        except ValueError:
            continue
        if amount > 0:
            out.append(Bucket(float(amount), day))
    return out


def buckets_from_cycle_totals(
    totals: dict[str, Any] | None, *, legacy_key: str, fallback_date: dt.date
) -> list[Bucket]:
    """Baldes do ciclo anterior, com queda para o formato antigo.

    Ciclo da Onda 5 em diante tem `carry_buckets`. Ciclo mais velho tem só o
    número em `legacy_key` — ele é convertido num balde datado no fim daquele
    ciclo. Sem isso, ligar a validade apagaria o saldo histórico de todo mundo
    de uma vez.
    """
    if not totals:
        return []
    buckets = buckets_from_json(totals.get("carry_buckets"))
    if buckets:
        return buckets
    legacy = totals.get(legacy_key)
    if isinstance(legacy, int | float) and legacy > 0:
        return [Bucket(float(legacy), fallback_date)]
    return []


def drop_expired(buckets: list[Bucket], *, on: dt.date, expires_days: int | None) -> list[Bucket]:
    """Remove o saldo cujo prazo terminou antes de `on` (início do ciclo novo).

    `expires_days=None` (ou <= 0) = sem validade, que é o padrão.
    """
    if expires_days is None or expires_days <= 0:
        return list(buckets)
    return [b for b in buckets if b.earned_on + dt.timedelta(days=expires_days) >= on]


def apply_cap(buckets: list[Bucket], *, cap: float | None) -> list[Bucket]:
    """Impõe o teto mantendo o saldo mais NOVO — o de maior vida útil restante."""
    if cap is None or cap < 0:
        return list(buckets)
    if cap == 0:
        return []
    kept: list[Bucket] = []
    room = cap
    for b in sorted(buckets, key=lambda x: x.earned_on, reverse=True):
        if room <= 0:
            break
        take = min(b.amount, room)
        kept.append(Bucket(take, b.earned_on))
        room -= take
    kept.sort(key=lambda x: x.earned_on)
    return kept


def consume_fifo(buckets: list[Bucket], amount: float) -> list[Bucket]:
    """Gasta `amount` do saldo acumulado, do mais antigo para o mais novo.

    Devolve o que sobrou. Consumo maior que o saldo simplesmente zera — o
    excedente é problema do chamador (vira excedente do ciclo).
    """
    left = max(0.0, amount)
    out: list[Bucket] = []
    for b in sorted(buckets, key=lambda x: x.earned_on):
        if left <= 0:
            out.append(b)
            continue
        take = min(b.amount, left)
        left -= take
        rest = b.amount - take
        if rest > 0:
            out.append(Bucket(rest, b.earned_on))
    return out


def total(buckets: list[Bucket]) -> float:
    return round(sum(b.amount for b in buckets), 4)


@dataclass(frozen=True)
class CarryResult:
    """O que o fechamento precisa saber sobre o acúmulo."""

    carry_in: float
    carry_out: float
    buckets_out: list[Bucket]
    expired: float
    capped: float


def roll(
    *,
    previous: list[Bucket],
    consumed: float,
    base_franchise: float,
    period_start: dt.date,
    period_end: dt.date,
    accumulate: bool,
    cap: float | None,
    expires_days: int | None,
) -> CarryResult:
    """Roda o acúmulo de um ciclo: entra saldo velho, sai saldo novo.

    Ordem, e o motivo de cada passo:

    1. **Expira** o que venceu antes de o ciclo começar — saldo vencido não
       pode financiar consumo novo.
    2. **Aplica o teto** ao que entra. O teto é do contrato ("você carrega no
       máximo X"), então vale na entrada; aplicar só na saída deixaria o
       cliente usar, dentro do ciclo, mais do que o contrato permite carregar.
    3. **Consome FIFO** o saldo que entrou, e só depois a franquia do mês.
       Gastar primeiro o que vence antes é o que evita perda por expiração.
    4. **Gera o balde novo** com a franquia do mês não usada, datada no fim do
       ciclo.

    `expired` e `capped` voltam para o snapshot: saldo que some sem alguém
    poder ver por quê é a receita para uma discussão com o cliente sem
    resposta.
    """
    alive = drop_expired(previous, on=period_start, expires_days=expires_days)
    expired = round(total(previous) - total(alive), 4)

    capped_in = apply_cap(alive, cap=cap)
    capped = round(total(alive) - total(capped_in), 4)
    carry_in = total(capped_in)

    if not accumulate:
        # Contrato que não acumula: o saldo que entrou ainda vale para este
        # ciclo (ele foi gerado quando o contrato acumulava, ou veio de
        # migração), mas nada é levado adiante.
        return CarryResult(carry_in, 0.0, [], expired, capped)

    leftover = consume_fifo(capped_in, consumed)
    # A franquia do mês só sobra depois de o saldo antigo ter sido gasto.
    used_from_base = max(0.0, consumed - carry_in)
    unused_base = max(0.0, base_franchise - used_from_base)
    if unused_base > 0:
        leftover.append(Bucket(round(unused_base, 4), period_end))
    leftover.sort(key=lambda x: x.earned_on)
    return CarryResult(carry_in, total(leftover), leftover, expired, capped)
