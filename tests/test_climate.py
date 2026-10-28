"""Climate entity tests for ATC Cala."""

from __future__ import annotations


from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant

ENTITY_ID = "climate.living_room"


async def _setup(hass: HomeAssistant, mock_entry) -> None:
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()


async def test_entity_state(hass: HomeAssistant, mock_entry, patch_client):
    await _setup(hass, mock_entry)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == HVACMode.HEAT
    assert state.attributes["current_temperature"] == 20.6
    assert state.attributes["temperature"] == 21.0
    assert state.attributes["hvac_action"] == HVACAction.HEATING
    assert state.attributes["preset_mode"] == "comfort"


async def test_set_temperature_writes_comfort(hass: HomeAssistant, mock_entry, patch_client):
    await _setup(hass, mock_entry)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_TEMPERATURE: 22.5},
        blocking=True,
    )
    assert ("TempComfort", "22.5") in patch_client.put_calls[-1][1]
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["temperature"] == 22.5


async def test_set_temperature_in_eco_writes_offset(
    hass: HomeAssistant, mock_entry, patch_client
):
    patch_client._radiator["IdModoActual"] = "E"
    await _setup(hass, mock_entry)
    # Comfort 21 - offset 3 = 18
    assert hass.states.get(ENTITY_ID).attributes["temperature"] == 18.0
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_TEMPERATURE: 19.5},
        blocking=True,
    )
    assert ("TempEco", "1.5") in patch_client.put_calls[-1][1]


async def test_set_preset_eco(hass: HomeAssistant, mock_entry, patch_client):
    await _setup(hass, mock_entry)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PRESET_MODE: "eco"},
        blocking=True,
    )
    heaters, cambios = patch_client.put_calls[-1]
    assert ("IdModoActual", "E") in cambios
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes["preset_mode"] == "eco"


async def test_turn_off(hass: HomeAssistant, mock_entry, patch_client):
    await _setup(hass, mock_entry)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    assert ("Encendido", "false") in patch_client.put_calls[-1][1]
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == HVACMode.OFF


async def test_boost_preset(hass: HomeAssistant, mock_entry, patch_client):
    await _setup(hass, mock_entry)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PRESET_MODE: "boost"},
        blocking=True,
    )
    assert len(patch_client.boost_calls) == 1
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes["preset_mode"] == "boost"
