"""Base entity for ATC Cala."""

from __future__ import annotations

from pyatccala import Radiator

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MIN_TEMP, MODEL
from .coordinator import AtcCalaDataUpdateCoordinator


def manual_temperature(radiator: Radiator | None) -> float:
    """Temperature for starting Manual mode: the last Manual setpoint, else the current target."""
    if radiator is None:
        return MIN_TEMP
    if radiator.temp_forced is not None:
        return radiator.temp_forced
    return radiator.target_temperature or MIN_TEMP


class AtcCalaEntity(CoordinatorEntity[AtcCalaDataUpdateCoordinator]):
    """Base for entities tied to a single radiator."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: AtcCalaDataUpdateCoordinator, radiator_id: str
    ) -> None:
        super().__init__(coordinator)
        self._radiator_id = radiator_id
        self._attr_unique_id = radiator_id
        radiator = self.radiator
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, radiator_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=radiator.name if radiator else radiator_id,
            sw_version=radiator.software if radiator else None,
        )

    @property
    def radiator(self) -> Radiator | None:
        """The current radiator state from the coordinator, or None if it vanished."""
        return self.coordinator.data.get(self._radiator_id)

    @property
    def available(self) -> bool:
        radiator = self.radiator
        return (
            super().available and radiator is not None and not radiator.offline
        )
