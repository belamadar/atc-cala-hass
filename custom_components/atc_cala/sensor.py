"""Sensor platform for ATC Cala: what each radiator's own weekly schedule is doing."""

from __future__ import annotations

from datetime import datetime

from pyatccala.const import SLOT_COMFORT

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import PRESET_COMFORT, PRESET_ECO
from .coordinator import AtcCalaConfigEntry, AtcCalaDataUpdateCoordinator
from .entity import AtcCalaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtcCalaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up schedule sensors for all radiators in the installation."""
    coordinator = entry.runtime_data
    async_add_entities(
        entity
        for radiator_id in coordinator.data
        for entity in (
            AtcCalaScheduledPresetSensor(coordinator, radiator_id),
            AtcCalaNextScheduleChangeSensor(coordinator, radiator_id),
        )
    )


def _preset(slot: str | None) -> str | None:
    if slot is None:
        return None
    return PRESET_COMFORT if slot == SLOT_COMFORT else PRESET_ECO


class AtcCalaScheduledPresetSensor(AtcCalaEntity, SensorEntity):
    """The preset the radiator's weekly schedule calls for right now."""

    _attr_translation_key = "scheduled_preset"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [PRESET_COMFORT, PRESET_ECO]

    def __init__(self, coordinator: AtcCalaDataUpdateCoordinator, radiator_id: str) -> None:
        super().__init__(coordinator, radiator_id)
        self._attr_unique_id = f"{radiator_id}_scheduled_preset"

    @property
    def native_value(self) -> str | None:
        radiator = self.radiator
        now = self.coordinator.installation_now()
        if radiator is None or now is None:
            return None
        return _preset(radiator.scheduled_slot(now))


class AtcCalaNextScheduleChangeSensor(AtcCalaEntity, SensorEntity):
    """When the radiator's weekly schedule next switches between Comfort and Eco."""

    _attr_translation_key = "next_schedule_change"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: AtcCalaDataUpdateCoordinator, radiator_id: str) -> None:
        super().__init__(coordinator, radiator_id)
        self._attr_unique_id = f"{radiator_id}_next_schedule_change"

    def _next(self) -> tuple[datetime, str] | None:
        radiator = self.radiator
        now = self.coordinator.installation_now()
        if radiator is None or now is None:
            return None
        return radiator.next_schedule_change(now)

    @property
    def native_value(self) -> datetime | None:
        change = self._next()
        return self.coordinator.installation_to_utc(change[0]) if change else None

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        change = self._next()
        return {"next_preset": _preset(change[1]) if change else None}
