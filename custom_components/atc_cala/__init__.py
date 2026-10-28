"""The ATC Cala integration."""

from __future__ import annotations

from pyatccala import AtcCalaClient

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_INSTALLATION_ID
from .coordinator import AtcCalaConfigEntry, AtcCalaDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR]


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

    if helpers := list(set(coordinator.schedule_helpers.values())):
        # React to helper changes right away; edits that don't change its state are
        # still picked up by the regular poll, which compares the full week.
        @callback
        def _helper_changed(event: Event[EventStateChangedData]) -> None:
            entry.async_create_background_task(
                hass, coordinator.async_request_refresh(), "atc_cala_schedule_sync"
            )

        entry.async_on_unload(
            async_track_state_change_event(hass, helpers, _helper_changed)
        )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AtcCalaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: AtcCalaConfigEntry) -> None:
    """Reload the entry when its options change (e.g. poll interval)."""
    await hass.config_entries.async_reload(entry.entry_id)
