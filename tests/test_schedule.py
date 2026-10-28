"""Tests for schedule helper sync, schedule sensors and schedule-mode setpoints."""

from __future__ import annotations

from datetime import datetime

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.atc_cala.const import CONF_SCHEDULE_HELPERS

# The schedule helper (HA core) keeps a timer for its next on/off transition.
pytestmark = pytest.mark.parametrize("expected_lingering_timers", [True])

RAD_ID = "000C01234567890"
HELPER = "schedule.heating"
WEEKDAY = "E" * 14 + "C" * 4 + "E" * 30  # Comfort 07:00-09:00


async def _setup(hass: HomeAssistant, mock_entry, *, link: bool = True) -> None:
    assert await async_setup_component(
        hass,
        "schedule",
        {
            "schedule": {
                "heating": {
                    "name": "Heating",
                    "monday": [{"from": "07:00:00", "to": "09:00:00"}],
                    "sunday": [{"from": "20:00:00", "to": "24:00:00"}],
                }
            }
        },
    )
    mock_entry.add_to_hass(hass)
    if link:
        hass.config_entries.async_update_entry(
            mock_entry, options={CONF_SCHEDULE_HELPERS: {RAD_ID: HELPER}}
        )
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()


def _schedule_uploads(patch_client) -> list[dict[str, str]]:
    return [
        dict(cambios)
        for _heaters, cambios in patch_client.put_calls
        if any(campo.startswith("Programacion") for campo, _ in cambios)
    ]


async def test_helper_is_synced_once(hass: HomeAssistant, mock_entry, patch_client):
    await _setup(hass, mock_entry)
    uploads = _schedule_uploads(patch_client)
    assert len(uploads) == 1
    assert uploads[0]["ProgramacionL"] == WEEKDAY
    assert uploads[0]["ProgramacionD"] == "E" * 40 + "C" * 8  # 24:00 = end of day
    assert uploads[0]["ProgramacionM"] == "E" * 48

    # The radiator now matches the helper, so the next poll uploads nothing.
    await mock_entry.runtime_data.async_refresh()
    assert len(_schedule_uploads(patch_client)) == 1


async def test_unlinked_radiator_is_left_alone(hass: HomeAssistant, mock_entry, patch_client):
    await _setup(hass, mock_entry, link=False)
    assert _schedule_uploads(patch_client) == []


async def test_schedule_sensors(
    hass: HomeAssistant, mock_entry, patch_client, freezer: FrozenDateTimeFactory
):
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to(datetime(2026, 7, 13, 8, 0, tzinfo=dt_util.UTC))  # a Monday
    await _setup(hass, mock_entry)
    await mock_entry.runtime_data.async_refresh()  # pick up the synced schedule
    await hass.async_block_till_done()

    preset = hass.states.get("sensor.living_room_scheduled_preset")
    assert preset.state == "comfort"
    change = hass.states.get("sensor.living_room_next_schedule_change")
    assert change.state == "2026-07-13T09:00:00+00:00"
    assert change.attributes["next_preset"] == "eco"


SELECT = "select.living_room_schedule_helper"


async def _select(hass: HomeAssistant, option: str) -> None:
    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: SELECT, "option": option}, blocking=True
    )
    await hass.async_block_till_done()


async def test_select_links_helper_without_reload(
    hass: HomeAssistant, mock_entry, patch_client
):
    await _setup(hass, mock_entry, link=False)
    state = hass.states.get(SELECT)
    assert state.state == "none"
    assert state.attributes["options"] == ["none", "Heating"]
    coordinator = mock_entry.runtime_data

    await _select(hass, "Heating")
    assert mock_entry.options[CONF_SCHEDULE_HELPERS] == {RAD_ID: HELPER}
    assert hass.states.get(SELECT).state == "Heating"
    assert len(_schedule_uploads(patch_client)) == 1  # uploaded right away
    assert mock_entry.runtime_data is coordinator  # no reload


async def test_select_unlinks_helper(hass: HomeAssistant, mock_entry, patch_client):
    await _setup(hass, mock_entry)
    assert hass.states.get(SELECT).state == "Heating"
    await _select(hass, "none")
    assert mock_entry.options[CONF_SCHEDULE_HELPERS] == {}
    assert hass.states.get(SELECT).state == "none"


async def test_select_follows_new_helpers(hass: HomeAssistant, mock_entry, patch_client):
    await _setup(hass, mock_entry, link=False)
    hass.states.async_set("schedule.holiday", "off", {"friendly_name": "Holiday"})
    await hass.async_block_till_done()
    assert hass.states.get(SELECT).attributes["options"] == ["none", "Heating", "Holiday"]


async def test_options_flow_keeps_helper_links(hass: HomeAssistant, mock_entry, patch_client):
    await _setup(hass, mock_entry)
    result = await hass.config_entries.options.async_init(mock_entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"poll_interval": 120, "boost_minutes": 60}
    )
    await hass.async_block_till_done()
    assert mock_entry.options["poll_interval"] == 120
    assert mock_entry.options[CONF_SCHEDULE_HELPERS] == {RAD_ID: HELPER}


async def test_set_temperature_in_schedule_mode(hass: HomeAssistant, mock_entry, patch_client):
    patch_client._radiator.update(
        {"IdModoActual": "P", **{f"Programacion{d}": "E" * 48 for d in "LMXJVSD"}}
    )
    await _setup(hass, mock_entry, link=False)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: "climate.living_room", ATTR_TEMPERATURE: 19},
        blocking=True,
    )
    # Current slot is Eco -> Eco offset below Comfort 21.
    assert ("TempEco", "2") in patch_client.put_calls[-1][1]
