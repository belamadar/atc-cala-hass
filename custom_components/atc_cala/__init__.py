"""The ATC Cala integration."""

from __future__ import annotations

from pyatccala import AtcCalaClient

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_INSTALLATION_ID
from .coordinator import AtcCalaConfigEntry, AtcCalaDataUpdateCoordinator, options_requiring_reload

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SELECT, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: AtcCalaConfigEntry) -> bool:
    """Set up ATC Cala from a config entry."""
    client = AtcCalaClient(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        session=async_get_clientsession(hass),
    )
    coordinator = AtcCalaDataUpdateCoordinator(
        hass, entry, client, entry.data[CONF_INSTALLATION_ID]
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    coordinator.async_track_schedule_helpers()
    entry.async_on_unload(coordinator.async_untrack_schedule_helpers)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AtcCalaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: AtcCalaConfigEntry) -> None:
    """Apply changed options: re-link schedule helpers in place, reload for anything else."""
    coordinator = entry.runtime_data
    if options_requiring_reload(entry.options) != coordinator.reload_options:
        await hass.config_entries.async_reload(entry.entry_id)
        return
    coordinator.async_track_schedule_helpers()
    coordinator.async_update_listeners()  # the schedule helper selects show the new link
    await coordinator.async_request_refresh()  # uploads the newly linked schedule
