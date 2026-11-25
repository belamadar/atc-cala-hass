"""Sensor platform for ATC Cala: each radiator's weekly schedule and energy use."""

from __future__ import annotations

from datetime import datetime

from pyatccala.const import SLOT_COMFORT

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
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
    """Set up schedule and energy sensors for all radiators in the installation."""
    coordinator = entry.runtime_data
    async_add_entities(
        entity
        for radiator_id in coordinator.data
        for entity in (
            AtcCalaScheduledPresetSensor(coordinator, radiator_id),
            AtcCalaNextScheduleChangeSensor(coordinator, radiator_id),
            AtcCalaEnergyTodaySensor(coordinator, radiator_id),
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


class AtcCalaEnergyTodaySensor(AtcCalaEntity, SensorEntity):
    """The cloud's estimated consumption for today (installation time).

    Resets at the installation's midnight. As TOTAL_INCREASING, Home Assistant's long-term
    statistics treat each reset as a new cycle and keep the running total hour by hour,
    which is what the Energy dashboard reads.
    """

    _attr_translation_key = "energy_today"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: AtcCalaDataUpdateCoordinator, radiator_id: str) -> None:
        super().__init__(coordinator, radiator_id)
        self._attr_unique_id = f"{radiator_id}_energy_today"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.energy.async_add_listener(self._handle_coordinator_update)
        )

    @property
    def available(self) -> bool:
        energy = self.coordinator.energy
        return (
            super().available
            and energy.last_update_success
            and self._radiator_id in (energy.data or {})
        )

    @property
    def native_value(self) -> float | None:
        consumption = (self.coordinator.energy.data or {}).get(self._radiator_id)
        return consumption.total_kwh if consumption else None

    @property
    def extra_state_attributes(self) -> dict[str, float | None]:
        consumption = (self.coordinator.energy.data or {}).get(self._radiator_id)
        if consumption is None:
            return {}
        return {
            "off_peak_energy": consumption.offpeak_kwh,
            "peak_energy": consumption.peak_kwh,
        }
