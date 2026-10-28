"""The ATC Cala integration."""

from __future__ import annotations

from pyatccala import AtcCalaClient

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_INSTALLATION_ID
from .coordinator import AtcCalaConfigEntry, AtcCalaDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.CLIMATE]


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
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AtcCalaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: AtcCalaConfigEntry) -> None:
    """Reload the entry when its options change (e.g. poll interval)."""
    await hass.config_entries.async_reload(entry.entry_id)
