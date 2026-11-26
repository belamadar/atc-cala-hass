"""Datetime platform for ATC Cala: when each radiator's Manual mode ends."""

from __future__ import annotations

from datetime import datetime

from pyatccala import AtcCalaConnectionError

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AtcCalaConfigEntry, AtcCalaDataUpdateCoordinator
from .entity import AtcCalaEntity, manual_temperature


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtcCalaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a Manual mode end time for every radiator."""
    coordinator = entry.runtime_data
    async_add_entities(
        AtcCalaManualUntil(coordinator, radiator_id) for radiator_id in coordinator.data
    )


class AtcCalaManualUntil(AtcCalaEntity, DateTimeEntity):
    """End of the app's Manual mode: a temperature held until a date and time.

    Unknown while Manual mode is off. Setting it starts Manual mode, or moves its end if
    it is already on; the temperature is set on the climate entity.
    """

    _attr_translation_key = "manual_until"

    def __init__(self, coordinator: AtcCalaDataUpdateCoordinator, radiator_id: str) -> None:
        super().__init__(coordinator, radiator_id)
        self._attr_unique_id = f"{radiator_id}_manual_until"

    @property
    def native_value(self) -> datetime | None:
        radiator = self.radiator
        return radiator.boost_until if radiator else None

    async def async_set_value(self, value: datetime) -> None:
        radiator = self.radiator
        if radiator is None:
            raise HomeAssistantError("Radiator is unavailable")
        try:
            # pyatccala calls the app's Manual mode "boost".
            await self.coordinator.client.async_start_boost_until(
                [self._radiator_id], manual_temperature(radiator), value
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        except AtcCalaConnectionError as err:
            raise HomeAssistantError(f"Failed to set Manual mode: {err}") from err
        await self.coordinator.async_request_refresh()
