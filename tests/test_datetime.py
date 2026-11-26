"""Tests for the Manual mode end time (the app's Manual mode, pyatccala's boost)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from homeassistant.components.datetime import (
    ATTR_DATETIME,
    DOMAIN as DATETIME_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

ENTITY_ID = "datetime.living_room_manual_mode_until"
CLIMATE = "climate.living_room"


async def _setup(hass: HomeAssistant, mock_entry) -> None:
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    await hass.services.async_call(
        DATETIME_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_DATETIME: value},
        blocking=True,
    )


async def test_unknown_while_manual_is_off(hass: HomeAssistant, mock_entry, patch_client):
    await _setup(hass, mock_entry)
    assert hass.states.get(ENTITY_ID).state == STATE_UNKNOWN


async def test_setting_end_starts_manual(hass: HomeAssistant, mock_entry, patch_client):
    await _setup(hass, mock_entry)
    until = (dt_util.utcnow() + timedelta(days=3)).replace(microsecond=0)
    await _set(hass, until)

    changes = dict(patch_client.put_calls[-1][1])
    assert changes["ModoForzado"] == "true"
    assert changes["TempForzado"] == "22"  # the last Manual setpoint
    assert int(changes["TiempoForzado"]) == int(until.timestamp())

    await hass.async_block_till_done()
    assert dt_util.parse_datetime(hass.states.get(ENTITY_ID).state) == until
    assert hass.states.get(CLIMATE).attributes["preset_mode"] == "manual"


async def test_end_in_the_past_is_rejected(hass: HomeAssistant, mock_entry, patch_client):
    await _setup(hass, mock_entry)
    with pytest.raises(ServiceValidationError):
        await _set(hass, dt_util.utcnow() - timedelta(hours=1))
    assert patch_client.put_calls == []
