"""znuny_admin_sysconfig: cliente GI de calendário/jornada (Spec #4, Bloco D).

Mock de httpx para get/set; testes puros de Python para as guardas de forma
(`validate_setting_shape`) e allowlist (`ALLOWED_SETTINGS`) — estas NUNCA
tocam o Znuny, então não precisam de mock.
"""

from __future__ import annotations

import httpx
import pytest

from gerti_sidecar.integrations import znuny_admin_sysconfig as sysconfig

_BASE = "http://znuny/otrs/nph-genericinterface.pl/Webservice/GertiAdmin"
_TOKEN = "tok-admin"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ZNUNY_ADMIN_WS_URL", _BASE)
    monkeypatch.setenv("ZNUNY_WS_TOKEN", _TOKEN)


class _MockResp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _capturing_post(status_code: int, payload):
    captured: dict = {}

    async def post(self, url, **kw):
        captured["url"] = url
        captured["json"] = kw.get("json")
        return _MockResp(status_code, payload)

    return post, captured


# --------------------------------------------------------------------------- #
# ALLOWED_SETTINGS
# --------------------------------------------------------------------------- #
def test_allowlist_has_base_names_and_calendar_variants():
    assert "TimeWorkingHours" in sysconfig.ALLOWED_SETTINGS
    assert "TimeVacationDays" in sysconfig.ALLOWED_SETTINGS
    assert "TimeVacationDaysOneTime" in sysconfig.ALLOWED_SETTINGS
    assert "TimeZone" in sysconfig.ALLOWED_SETTINGS
    assert "CalendarWeekDayStart" in sysconfig.ALLOWED_SETTINGS
    assert "TimeWorkingHours::Calendar1" in sysconfig.ALLOWED_SETTINGS
    assert "TimeWorkingHours::Calendar9" in sysconfig.ALLOWED_SETTINGS
    assert "TimeVacationDays::Calendar5" in sysconfig.ALLOWED_SETTINGS
    assert "TimeVacationDaysOneTime::Calendar5" in sysconfig.ALLOWED_SETTINGS


def test_allowlist_excludes_unrelated_names_and_out_of_range_calendars():
    assert "SomeRandomSetting" not in sysconfig.ALLOWED_SETTINGS
    assert "TicketHook" not in sysconfig.ALLOWED_SETTINGS
    # TimeZone/CalendarWeekDayStart NÃO têm variante por calendário (contrato).
    assert "TimeZone::Calendar1" not in sysconfig.ALLOWED_SETTINGS
    assert "CalendarWeekDayStart::Calendar1" not in sysconfig.ALLOWED_SETTINGS
    assert "TimeWorkingHours::Calendar0" not in sysconfig.ALLOWED_SETTINGS
    assert "TimeWorkingHours::Calendar10" not in sysconfig.ALLOWED_SETTINGS


# --------------------------------------------------------------------------- #
# validate_setting_shape — jornada (TimeWorkingHours*)
# --------------------------------------------------------------------------- #
def test_jornada_valid_shape_ok():
    sysconfig.validate_setting_shape("TimeWorkingHours", {"Mon": [8, 9, 10], "Tue": [8, 17]})
    sysconfig.validate_setting_shape("TimeWorkingHours::Calendar3", {"Fri": [0, 23]})


@pytest.mark.parametrize(
    "value",
    [
        [],  # não é dict
        {"Monday": [8, 9]},  # dia fora de Mon..Sun
        {"Mon": "8,9"},  # horas não é lista
        {"Mon": []},  # lista vazia
        {"Mon": [24]},  # hora fora de 0-23
        {"Mon": [-1]},  # hora negativa
        {"Mon": [8.5]},  # hora não inteira
        {},  # vazio
    ],
)
def test_jornada_invalid_shape_raises(value):
    with pytest.raises(sysconfig.CalendarSettingInvalid):
        sysconfig.validate_setting_shape("TimeWorkingHours", value)


# --------------------------------------------------------------------------- #
# validate_setting_shape — feriado recorrente (TimeVacationDays)
# --------------------------------------------------------------------------- #
def test_feriado_valid_shape_ok():
    sysconfig.validate_setting_shape("TimeVacationDays", {"1": {"1": "Confraternização"}})
    sysconfig.validate_setting_shape("TimeVacationDays::Calendar2", {"12": {"25": "Natal"}})


@pytest.mark.parametrize(
    "value",
    [
        [],
        {"13": {"1": "x"}},  # mês inválido
        {"1": {"32": "x"}},  # dia inválido
        {"1": {"1": ""}},  # texto vazio
        {"1": {"1": 123}},  # texto não é string
        {"1": []},  # dias não é dict
        {},
    ],
)
def test_feriado_invalid_shape_raises(value):
    with pytest.raises(sysconfig.CalendarSettingInvalid):
        sysconfig.validate_setting_shape("TimeVacationDays", value)


# --------------------------------------------------------------------------- #
# validate_setting_shape — feriado pontual (TimeVacationDaysOneTime, um nível a mais)
# --------------------------------------------------------------------------- #
def test_feriado_pontual_valid_shape_ok():
    sysconfig.validate_setting_shape(
        "TimeVacationDaysOneTime", {"2026": {"12": {"25": "Natal 2026"}}}
    )


def test_feriado_pontual_rejects_two_level_shape_of_recurring_feriado():
    # Mesmo formato de TimeVacationDays (Mês->Dia->texto, sem Ano) é inválido aqui.
    with pytest.raises(sysconfig.CalendarSettingInvalid):
        sysconfig.validate_setting_shape("TimeVacationDaysOneTime", {"12": {"25": "Natal"}})


@pytest.mark.parametrize(
    "value",
    [
        {"26": {"12": {"25": "x"}}},  # ano não tem 4 dígitos
        {"2026": {"13": {"25": "x"}}},  # mês inválido
        {"2026": {"12": {"32": "x"}}},  # dia inválido
        {"2026": {"12": {"25": ""}}},  # texto vazio
        {},
    ],
)
def test_feriado_pontual_invalid_shape_raises(value):
    with pytest.raises(sysconfig.CalendarSettingInvalid):
        sysconfig.validate_setting_shape("TimeVacationDaysOneTime", value)


# --------------------------------------------------------------------------- #
# validate_setting_shape — escalares (TimeZone / CalendarWeekDayStart)
# --------------------------------------------------------------------------- #
def test_select_valid_shape_ok():
    sysconfig.validate_setting_shape("TimeZone", "America/Sao_Paulo")
    sysconfig.validate_setting_shape("CalendarWeekDayStart", 1)


@pytest.mark.parametrize("value", [None, "", [], {}])
def test_select_invalid_shape_raises(value):
    with pytest.raises(sysconfig.CalendarSettingInvalid):
        sysconfig.validate_setting_shape("TimeZone", value)


# --------------------------------------------------------------------------- #
# get_setting / set_setting (GI)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_get_setting_happy(monkeypatch):
    post, captured = _capturing_post(
        200,
        {
            "Settings": {
                "TimeWorkingHours": {
                    "Name": "TimeWorkingHours",
                    "EffectiveValue": {"Mon": [8, 9, 10]},
                    "IsValid": 1,
                    "IsDirty": 0,
                }
            }
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    result = await sysconfig.get_setting("TimeWorkingHours", agent_login="william")

    assert captured["url"] == _BASE + "/SysConfig/Get"
    assert captured["json"]["Name"] == "TimeWorkingHours"
    assert captured["json"]["AgentLogin"] == "william"
    assert result.name == "TimeWorkingHours"
    assert result.value == {"Mon": [8, 9, 10]}


@pytest.mark.asyncio
async def test_get_setting_missing_in_response_raises_write_error(monkeypatch):
    post, _ = _capturing_post(200, {"Settings": {}})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(sysconfig.ZnunyWriteError):
        await sysconfig.get_setting("TimeWorkingHours", agent_login="william")


@pytest.mark.asyncio
async def test_set_setting_happy(monkeypatch):
    post, captured = _capturing_post(
        200,
        {
            "Name": "TimeWorkingHours",
            "EffectiveValue": {"Mon": [8, 9]},
            "UserID": 3,
            "Deployed": 1,
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    result = await sysconfig.set_setting("TimeWorkingHours", {"Mon": [8, 9]}, agent_login="william")

    assert captured["url"] == _BASE + "/SysConfig/Set"
    body = captured["json"]
    assert body["Name"] == "TimeWorkingHours"
    assert body["EffectiveValue"] == {"Mon": [8, 9]}
    assert body["AgentLogin"] == "william"
    assert result.value == {"Mon": [8, 9]}


@pytest.mark.asyncio
async def test_set_setting_lock_failed_raises_write_error(monkeypatch):
    post, _ = _capturing_post(
        200,
        {"Error": {"ErrorMessage": "could not lock setting 'TimeWorkingHours'"}},
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(sysconfig.ZnunyWriteError, match="lock"):
        await sysconfig.set_setting("TimeWorkingHours", {"Mon": [8]}, agent_login="william")


@pytest.mark.asyncio
async def test_transport_error_raises_unavailable(monkeypatch):
    async def boom(self, url, **kw):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(httpx.AsyncClient, "post", boom)

    with pytest.raises(sysconfig.ZnunyUnavailable):
        await sysconfig.get_setting("TimeWorkingHours", agent_login="william")


# --------------------------------------------------------------------------- #
# is_valid_calendar_suffix / calendar_setting_names (contrato COMPOSTO)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("calendar", ["", "1", "5", "9"])
def test_is_valid_calendar_suffix_accepts_default_and_1_to_9(calendar):
    assert sysconfig.is_valid_calendar_suffix(calendar) is True


@pytest.mark.parametrize("calendar", ["0", "10", "abc", "Calendar1", "-1", " "])
def test_is_valid_calendar_suffix_rejects_anything_else(calendar):
    assert sysconfig.is_valid_calendar_suffix(calendar) is False


def test_calendar_setting_names_default_calendar_has_no_suffix():
    names = sysconfig.calendar_setting_names("")
    assert names.working_hours == "TimeWorkingHours"
    assert names.vacation_days == "TimeVacationDays"
    assert names.vacation_days_one_time == "TimeVacationDaysOneTime"


def test_calendar_setting_names_numbered_calendar_has_suffix():
    names = sysconfig.calendar_setting_names("3")
    assert names.working_hours == "TimeWorkingHours::Calendar3"
    assert names.vacation_days == "TimeVacationDays::Calendar3"
    assert names.vacation_days_one_time == "TimeVacationDaysOneTime::Calendar3"


# --------------------------------------------------------------------------- #
# get_settings (bulk, GI) — GET composto do calendário
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_get_settings_happy_fetches_all_in_one_call(monkeypatch):
    post, captured = _capturing_post(
        200,
        {
            "Settings": {
                "TimeWorkingHours": {
                    "Name": "TimeWorkingHours",
                    "EffectiveValue": {"Mon": [8, 9]},
                },
                "TimeVacationDays": {
                    "Name": "TimeVacationDays",
                    "EffectiveValue": {"1": {"1": "Confraternização"}},
                },
                "TimeVacationDaysOneTime": {
                    "Name": "TimeVacationDaysOneTime",
                    "EffectiveValue": {"2026": {"12": {"25": "Natal"}}},
                },
            }
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    names = ["TimeWorkingHours", "TimeVacationDays", "TimeVacationDaysOneTime"]
    result = await sysconfig.get_settings(names, agent_login="william")

    assert captured["url"] == _BASE + "/SysConfig/Get"
    assert captured["json"]["Names"] == names
    assert captured["json"]["AgentLogin"] == "william"
    assert result["TimeWorkingHours"].value == {"Mon": [8, 9]}
    assert result["TimeVacationDays"].value == {"1": {"1": "Confraternização"}}
    assert result["TimeVacationDaysOneTime"].value == {"2026": {"12": {"25": "Natal"}}}


@pytest.mark.asyncio
async def test_get_settings_missing_one_in_response_raises_write_error(monkeypatch):
    post, _ = _capturing_post(
        200,
        {
            "Settings": {
                "TimeWorkingHours": {"Name": "TimeWorkingHours", "EffectiveValue": {"Mon": [8]}},
                # TimeVacationDays ausente na resposta.
            }
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(sysconfig.ZnunyWriteError):
        await sysconfig.get_settings(
            ["TimeWorkingHours", "TimeVacationDays"], agent_login="william"
        )
