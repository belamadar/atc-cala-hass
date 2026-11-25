"""Tests for the energy sensor."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from pyatccala import AtcCalaConnectionError
from pytest_homeassistant.common import async_fire_time_changed

from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorStateClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant

from custom_components.atc_cala.const import ENERGY_POLL_INTERVAL

ENERGY = "sensor.living_room_energy_today"


async def _setup(hass: HomeAssistant, mock_entry) -> None:
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()


async def test_energy_today(hass: HomeAssistant, mock_entry):
    await _setup(hass, mock_entry)
    state = hass.states.get(ENERGY)
    assert float(state.state) == 0.178 + 0.419
    assert state.attributes[ATTR_DEVICE_CLASS] == "energy"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "kWh"
    assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL_INCREASING
    assert state.attributes["off_peak_energy"] == 0.178
    assert state.attributes["peak_energy"] == 0.419


async def test_energy_polls_on_its_own_interval(
    hass: HomeAssistant, mock_entry, patch_client, freezer: FrozenDateTimeFactory
):
    await _setup(hass, mock_entry)
    patch_client.consumption["ConsumoTotalPico"] = 1.0

    # The state poll (60 s) does not refetch energy.
    freezer.tick(120)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert float(hass.states.get(ENERGY).state) == 0.178 + 0.419

    freezer.tick(ENERGY_POLL_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert float(hass.states.get(ENERGY).state) == 0.178 + 1.0


async def test_energy_failure_does_not_block_setup(
    hass: HomeAssistant, mock_entry, patch_client
):
    patch_client.consumption_error = AtcCalaConnectionError("boom")
    await _setup(hass, mock_entry)
    assert hass.states.get(ENERGY).state == STATE_UNAVAILABLE
    assert hass.states.get("climate.living_room").state == "heat"  # the rest still works
