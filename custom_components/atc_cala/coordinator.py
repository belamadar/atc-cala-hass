"""Data update coordinator for ATC Cala."""

from __future__ import annotations

import logging
from datetime import timedelta

from pyatccala import (
    AtcCalaAuthError,
    AtcCalaClient,
    AtcCalaConnectionError,
    Radiator,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type AtcCalaConfigEntry = ConfigEntry["AtcCalaDataUpdateCoordinator"]


class AtcCalaDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Radiator]]):
    """Polls the ATC Cala cloud and exposes radiators keyed by IdRadiador."""

    config_entry: AtcCalaConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: AtcCalaConfigEntry,
        client: AtcCalaClient,
        installation_id: int,
    ) -> None:
        interval = config_entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=interval),
            always_update=False,
        )
        self.client = client
        self.installation_id = installation_id

    async def _async_update_data(self) -> dict[str, Radiator]:
        try:
            await self.client.async_ensure_token()
            radiators = await self.client.get_radiators(self.installation_id)
        except AtcCalaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AtcCalaConnectionError as err:
            raise UpdateFailed(str(err)) from err
        return {r.id_radiator: r for r in radiators}
