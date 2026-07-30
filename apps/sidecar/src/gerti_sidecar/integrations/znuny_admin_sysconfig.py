"""Cliente GI de SysConfig — calendário e jornada (Spec #4, Bloco D).

Mesmo padrão de `znuny_admin_people.py`: webservice `GertiAdmin` (base
`ZNUNY_ADMIN_WS_URL`), `AccessToken` = `ZNUNY_WS_TOKEN`. Operações GI do
contrato: `AdminSysConfigGet` (Route `/SysConfig/Get`), `AdminSysConfigSet`
(Route `/SysConfig/Set`) — nomes de Route e de campo (`Name`,
`EffectiveValue`, `AgentLogin`) espelham exatamente
`znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminSysConfigGet.pm`
e `AdminSysConfigSet.pm` (implementação irmã desta mesma spec).

Este é o único bloco onde um erro afeta a instância inteira (contrato, Bloco
D). Duas guardas vivem AQUI, antes de qualquer chamada ao Znuny (espelhando
os dois primeiros guards do lado Perl):

1. **Allowlist fechada** (`ALLOWED_SETTINGS`) — nome fora da lista nem chega
   a montar request; o router devolve 404 sem tocar no GI.
2. **Validação de forma** (`validate_setting_shape`) — jornada
   (`TimeWorkingHours*`) é `Dia -> lista de horas inteiras 0-23`; feriado
   recorrente (`TimeVacationDays*`, exceto OneTime) é `Mês -> Dia -> texto`;
   feriado pontual (`TimeVacationDaysOneTime*`) é
   `Ano -> Mês -> Dia -> texto` (um nível a mais — confirmado no
   `_ValidateShape` do lado Perl); `TimeZone`/`CalendarWeekDayStart` são
   escalares simples. Forma errada -> `CalendarSettingInvalid`, que o router
   mapeia para 422 sem tocar no Znuny.

O fluxo `SettingLock -> SettingUpdate -> ConfigurationDeploy` (com liberação
garantida do lock em caso de erro) é responsabilidade da operação Perl
`AdminSysConfigSet` — o sidecar faz uma única chamada GI POR SETTING e
repassa o resultado; não orquestra lock/update/deploy, só a sequência de
chamadas.

Contrato do router (`admin_znuny_people.py`) é a forma COMPOSTA: a tela
`/znuny/calendario` fala em "um calendário" (jornada + feriado recorrente +
feriado pontual juntos), não em settings avulsos. `get_settings` busca os
três de uma vez (o Perl aceita `Names` em lista); `set_setting` ainda grava
um por vez porque `AdminSysConfigSet` só sabe lockar/atualizar/deployar UM
`Name` por chamada — o router é quem chama três vezes em sequência e lida
com aplicação parcial se uma delas falhar no meio.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from gerti_sidecar.integrations.znuny_customer_admin import (
    ZnunyUnavailable,
    ZnunyWriteError,
)

__all__ = [
    "ALLOWED_SETTINGS",
    "CalendarSetting",
    "CalendarSettingInvalid",
    "CalendarSettingNames",
    "ZnunyUnavailable",
    "ZnunyWriteError",
    "calendar_setting_names",
    "get_setting",
    "get_settings",
    "is_valid_calendar_suffix",
    "set_setting",
    "validate_setting_shape",
]

_TIMEOUT = 10.0

_CALENDAR_SUFFIXES = [f"Calendar{n}" for n in range(1, 10)]

# Allowlist fechada (contrato Bloco D): só estes nomes são legíveis/graváveis.
ALLOWED_SETTINGS: frozenset[str] = frozenset(
    {
        "TimeWorkingHours",
        "TimeVacationDays",
        "TimeVacationDaysOneTime",
        "TimeZone",
        "CalendarWeekDayStart",
    }
    | {f"TimeWorkingHours::{c}" for c in _CALENDAR_SUFFIXES}
    | {f"TimeVacationDays::{c}" for c in _CALENDAR_SUFFIXES}
    | {f"TimeVacationDaysOneTime::{c}" for c in _CALENDAR_SUFFIXES}
)

_WEEKDAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}

# Sufixos de calendário aceitos na forma COMPOSTA do contrato (tela
# `/znuny/calendario`): '' = calendário padrão, '1'..'9' = Calendar1..Calendar9.
# Espelha exatamente `CALENDAR_OPTIONS` de `useWorkingHours.ts` no console.
_CALENDAR_SUFFIX_VALUES: frozenset[str] = frozenset(str(n) for n in range(1, 10))


class CalendarSettingInvalid(ValueError):
    """Forma de jornada/feriado inválida -> 422 no router, sem tocar no Znuny."""


@dataclass(frozen=True)
class CalendarSetting:
    name: str
    value: Any


@dataclass(frozen=True)
class CalendarSettingNames:
    """Os três nomes de setting do SysConfig que compõem UM calendário na
    forma composta do contrato (jornada + feriado recorrente + feriado
    pontual)."""

    working_hours: str
    vacation_days: str
    vacation_days_one_time: str


def is_valid_calendar_suffix(calendar: str) -> bool:
    """`calendar` vem da query/body como '' (padrão) ou '1'..'9'
    (Calendar1..Calendar9). Qualquer outro valor ('0', '10', 'abc', ...) é
    desconhecido -> 404 no router, ANTES de montar qualquer nome de setting
    ou tocar no Znuny (mesmo padrão de "recurso desconhecido" das outras
    rotas do sidecar)."""
    return calendar == "" or calendar in _CALENDAR_SUFFIX_VALUES


def calendar_setting_names(calendar: str) -> CalendarSettingNames:
    """Traduz o sufixo de calendário ('' ou '1'..'9') nos três nomes de
    setting do SysConfig. Chamador deve validar com `is_valid_calendar_suffix`
    antes — esta função não valida, só monta os nomes."""
    suffix = f"::Calendar{calendar}" if calendar else ""
    return CalendarSettingNames(
        working_hours=f"TimeWorkingHours{suffix}",
        vacation_days=f"TimeVacationDays{suffix}",
        vacation_days_one_time=f"TimeVacationDaysOneTime{suffix}",
    )


def _resolve_admin_endpoint() -> tuple[str, str]:
    base = os.environ.get("ZNUNY_ADMIN_WS_URL", "")
    token = os.environ.get("ZNUNY_WS_TOKEN", "")
    return base, token


async def _post(route: str, body: dict[str, Any]) -> dict[str, Any]:
    base, token = _resolve_admin_endpoint()
    url = base.rstrip("/") + route
    payload = {"AccessToken": token, **body}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise ZnunyUnavailable(str(exc)) from exc
    if resp.status_code >= 500:
        raise ZnunyUnavailable(f"znuny http {resp.status_code}")
    if resp.status_code >= 400:
        message = _error_message(_safe_json(resp)) or f"znuny http {resp.status_code}"
        raise ZnunyWriteError(message)
    data = _safe_json(resp)
    if data is None:
        raise ZnunyUnavailable("resposta não-JSON do Znuny")
    if "Error" in data:
        raise ZnunyWriteError(_error_message(data) or "znuny rejeitou a operação")
    return data


def _safe_json(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _error_message(data: dict[str, Any] | None) -> str:
    if not data:
        return ""
    err = data.get("Error")
    if isinstance(err, dict):
        return str(err.get("ErrorMessage") or err.get("ErrorCode") or err or "znuny error")
    if err:
        return str(err)
    return ""


def _int_in_range(value: Any, lo: int, hi: int) -> bool:
    # bool é subclasse de int (rejeita); float rejeita mesmo quando "inteiro"
    # (8.5 não é uma hora válida, e não queremos truncar silenciosamente).
    if isinstance(value, bool) or isinstance(value, float):
        return False
    try:
        n = int(value)
    except (TypeError, ValueError):
        return False
    return lo <= n <= hi


def _validate_jornada(value: Any) -> None:
    """Dia -> lista de horas inteiras 0-23."""
    if not isinstance(value, dict) or not value:
        raise CalendarSettingInvalid("jornada precisa ser um objeto {dia: [horas]} não vazio")
    for day, hours in value.items():
        if day not in _WEEKDAYS:
            raise CalendarSettingInvalid(f"dia inválido na jornada: {day!r} (esperado Mon..Sun)")
        if not isinstance(hours, list) or not hours:
            raise CalendarSettingInvalid(f"horas de {day} precisam ser uma lista não vazia")
        for h in hours:
            if not _int_in_range(h, 0, 23):
                raise CalendarSettingInvalid(
                    f"hora inválida em {day}: {h!r} (esperado inteiro 0-23)"
                )


def _validate_feriado(value: Any) -> None:
    """Mês -> Dia -> texto (TimeVacationDays, recorrente)."""
    if not isinstance(value, dict) or not value:
        raise CalendarSettingInvalid("feriado precisa ser um objeto {mês: {dia: texto}} não vazio")
    for month, days in value.items():
        if not _int_in_range(month, 1, 12):
            raise CalendarSettingInvalid(f"mês inválido: {month!r} (esperado 1-12)")
        if not isinstance(days, dict) or not days:
            raise CalendarSettingInvalid(f"dias do mês {month} precisam ser um objeto não vazio")
        for day, text in days.items():
            if not _int_in_range(day, 1, 31):
                raise CalendarSettingInvalid(f"dia inválido: {day!r} (esperado 1-31)")
            if not isinstance(text, str) or not text.strip():
                raise CalendarSettingInvalid(
                    f"texto do feriado {month}/{day} precisa ser texto não vazio"
                )


def _validate_feriado_pontual(value: Any) -> None:
    """Ano -> Mês -> Dia -> texto (TimeVacationDaysOneTime — um nível a mais)."""
    if not isinstance(value, dict) or not value:
        raise CalendarSettingInvalid(
            "feriado pontual precisa ser um objeto {ano: {mês: {dia: texto}}} não vazio"
        )
    for year, months in value.items():
        if not (isinstance(year, int) and not isinstance(year, bool)) and not (
            isinstance(year, str) and year.isdigit() and len(year) == 4
        ):
            raise CalendarSettingInvalid(f"ano inválido: {year!r} (esperado 4 dígitos)")
        if not isinstance(months, dict) or not months:
            raise CalendarSettingInvalid(f"meses do ano {year} precisam ser um objeto não vazio")
        for month, days in months.items():
            if not _int_in_range(month, 1, 12):
                raise CalendarSettingInvalid(f"mês inválido: {month!r} (esperado 1-12)")
            if not isinstance(days, dict) or not days:
                raise CalendarSettingInvalid(
                    f"dias do mês {year}-{month} precisam ser um objeto não vazio"
                )
            for day, text in days.items():
                if not _int_in_range(day, 1, 31):
                    raise CalendarSettingInvalid(f"dia inválido: {day!r} (esperado 1-31)")
                if not isinstance(text, str) or not text.strip():
                    raise CalendarSettingInvalid(
                        f"texto do feriado {year}-{month}-{day} precisa ser texto não vazio"
                    )


def _validate_select(value: Any) -> None:
    """TimeZone / CalendarWeekDayStart: escalar simples (não-ref), não vazio."""
    if isinstance(value, dict | list):
        raise CalendarSettingInvalid("valor precisa ser um escalar (não uma lista/objeto)")
    if value is None or value == "":
        raise CalendarSettingInvalid("valor não pode ser vazio")


def validate_setting_shape(name: str, value: Any) -> None:
    """Valida a FORMA do valor conforme a família do setting. Levanta
    `CalendarSettingInvalid` (nunca chama o Znuny) se a forma estiver errada.

    Espelha `_SettingKind`/`_ValidateShape` de `AdminSysConfigSet.pm`.
    """
    base = name.split("::", 1)[0]
    if base == "TimeWorkingHours":
        _validate_jornada(value)
    elif base == "TimeVacationDays":
        _validate_feriado(value)
    elif base == "TimeVacationDaysOneTime":
        _validate_feriado_pontual(value)
    elif base in ("TimeZone", "CalendarWeekDayStart"):
        _validate_select(value)
    else:  # defesa em profundidade — não deve ocorrer p/ nome na allowlist
        raise CalendarSettingInvalid(f"setting sem validador de forma: {name}")


async def get_setting(name: str, *, agent_login: str) -> CalendarSetting:
    data = await _post("/SysConfig/Get", {"Name": name, "AgentLogin": agent_login})
    settings = data.get("Settings") or {}
    setting = settings.get(name)
    if not isinstance(setting, dict):
        raise ZnunyWriteError(f"setting '{name}' não encontrado na resposta do Znuny")
    return CalendarSetting(
        name=str(setting.get("Name") or name), value=setting.get("EffectiveValue")
    )


async def get_settings(names: list[str], *, agent_login: str) -> dict[str, CalendarSetting]:
    """Busca vários settings em UMA chamada GI: `AdminSysConfigGet` aceita
    `Names` como lista (ver `Run()` em `AdminSysConfigGet.pm`) e devolve todos
    de uma vez. Usado pelo GET composto do calendário (Bloco D): jornada +
    feriado recorrente + feriado pontual do MESMO calendário numa única ida
    ao Znuny, em vez de três.
    """
    data = await _post("/SysConfig/Get", {"Names": names, "AgentLogin": agent_login})
    settings = data.get("Settings") or {}
    result: dict[str, CalendarSetting] = {}
    for name in names:
        setting = settings.get(name)
        if not isinstance(setting, dict):
            raise ZnunyWriteError(f"setting '{name}' não encontrado na resposta do Znuny")
        result[name] = CalendarSetting(
            name=str(setting.get("Name") or name), value=setting.get("EffectiveValue")
        )
    return result


async def set_setting(name: str, value: Any, *, agent_login: str) -> CalendarSetting:
    data = await _post(
        "/SysConfig/Set",
        {"Name": name, "EffectiveValue": value, "AgentLogin": agent_login},
    )
    return CalendarSetting(
        name=str(data.get("Name") or name), value=data.get("EffectiveValue", value)
    )
