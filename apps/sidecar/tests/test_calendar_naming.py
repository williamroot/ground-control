"""T-R13.2 e T-R13.3 — as arestas de calendário do R13a.

Duas pendências honestas registradas no levantamento, fechadas aqui.

**T-R13.2 — não dava para nomear um calendário.** A tela de filas mostrava
"Calendar 3 - " e ninguém sabia qual era o de São Paulo. O Znuny tem o setting
`TimeZone::Calendar<N>Name`; ele só não estava na allowlist.

**T-R13.3 — o levantamento dizia que "o console limita a 9 calendários; o
Znuny permite mais". A premissa estava ERRADA.** O `Framework.xml` da 7.2.3
define exatamente `Calendar1..Calendar9` — o limite é do Znuny, não nosso. Não
há divergência a corrigir; há um número a documentar, e um teste que falha se
alguém ampliar um lado sem o outro.
"""

from __future__ import annotations

import re

from gerti_sidecar.integrations.znuny_admin_sysconfig import (
    ALLOWED_SETTINGS,
    calendar_setting_names,
    is_valid_calendar_suffix,
)

# O que o Znuny 7.2.3 define (conferido no Framework.xml da imagem).
ZNUNY_CALENDARS = tuple(range(1, 10))


def test_the_limit_is_znunys_own_not_ours():
    """T-R13.3 — nove é o número do Znuny. Não é teto inventado pelo console."""
    for n in ZNUNY_CALENDARS:
        assert is_valid_calendar_suffix(str(n)), f"Calendar{n} deveria ser aceito"
    # O décimo não existe no Znuny 7.2.3 — aceitar seria oferecer um calendário
    # que o Znuny ignora, e o operador só descobriria pelo SLA errado.
    assert not is_valid_calendar_suffix("10")
    assert not is_valid_calendar_suffix("0")
    assert is_valid_calendar_suffix(""), "o calendário padrão continua válido"


def test_the_allowlist_covers_exactly_the_nine_calendars():
    """Guarda contra ampliar um lado só.

    Se alguém acrescentar `Calendar10` à validação sem acrescentar os settings
    à allowlist (ou o contrário), este teste falha — em vez de o operador
    receber um 422 sem explicação na tela.
    """
    found = {
        int(m.group(1))
        for name in ALLOWED_SETTINGS
        if (m := re.search(r"Calendar(\d+)(?:Name)?$", name))
    }
    assert found == set(ZNUNY_CALENDARS)


def test_every_calendar_has_a_name_setting():
    """T-R13.2 — o nome entrou na allowlist para os nove."""
    for n in ZNUNY_CALENDARS:
        assert f"TimeZone::Calendar{n}Name" in ALLOWED_SETTINGS


def test_the_default_calendar_has_no_name():
    """Ele é "o calendário" — o Znuny não tem `TimeZone::Name`.

    Inventar um nome para o padrão faria o PUT tentar gravar um setting que
    não existe, e o Znuny recusaria com uma mensagem que ninguém entende.
    """
    assert calendar_setting_names("").name is None
    assert calendar_setting_names("3").name == "TimeZone::Calendar3Name"


def test_the_three_calendar_settings_keep_their_names():
    """Regressão: acrescentar o nome não pode ter mexido nos outros três."""
    names = calendar_setting_names("3")
    assert names.working_hours == "TimeWorkingHours::Calendar3"
    assert names.vacation_days == "TimeVacationDays::Calendar3"
    assert names.vacation_days_one_time == "TimeVacationDaysOneTime::Calendar3"


def test_the_allowlist_stays_closed():
    """O ponto do Bloco D: nada além do que está previsto entra."""
    for arbitrary in (
        "SecureMode",
        "ProductName",
        "TimeZone::Calendar10Name",
        "TimeWorkingHours::Calendar10",
        "DatabaseDSN",
    ):
        assert arbitrary not in ALLOWED_SETTINGS
