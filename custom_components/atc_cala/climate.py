"""Climate platform for ATC Cala radiators."""

from __future__ import annotations

from typing import Any

from pyatccala import AtcCalaConnectionError
from pyatccala.const import (
    FIELD_ENCENDIDO,
    FIELD_MODE,
    FIELD_MODO_FORZADO,
)

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_BOOST_MINUTES,
    DEFAULT_BOOST_MINUTES,
    MAX_TEMP,
    MIN_TEMP,
    MODE_TO_PRESET,
    PRESET_BOOST,
    PRESET_MODES,
    PRESET_TO_MODE,
    TEMP_STEP,
)
from .coordinator import AtcCalaConfigEntry, AtcCalaDataUpdateCoordinator
from .entity import AtcCalaEntity

async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtcCalaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up climate entities for all radiators in the installation."""
    coordinator = entry.runtime_data
    async_add_entities(
        AtcCalaClimate(coordinator, radiator_id) for radiator_id in coordinator.data
    )


class AtcCalaClimate(AtcCalaEntity, ClimateEntity):
    """A single ATC Cala radiator as a climate entity."""

    _attr_name = None  # the device name is the entity name (has_entity_name)
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = PRESET_MODES
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = TEMP_STEP
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(
        self, coordinator: AtcCalaDataUpdateCoordinator, radiator_id: str
    ) -> None:
        super().__init__(coordinator, radiator_id)

    # -- state (read) --------------------------------------------------------------

    @property
    def current_temperature(self) -> float | None:
        return self.radiator.current_temperature if self.radiator else None

    @property
    def target_temperature(self) -> float | None:
        return self.radiator.target_temperature if self.radiator else None

    @property
    def hvac_mode(self) -> HVACMode | None:
        radiator = self.radiator
        if radiator is None:
            return None
        return HVACMode.HEAT if radiator.on else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        radiator = self.radiator
        if radiator is None:
            return None
        if not radiator.on:
            return HVACAction.OFF
        return HVACAction.HEATING if radiator.heating else HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        radiator = self.radiator
        if radiator is None:
            return None
        if radiator.boost_active:
            return PRESET_BOOST
        return MODE_TO_PRESET.get(radiator.mode)

    # -- commands (write) ----------------------------------------------------------

    async def _apply(self, cambios: list[tuple[str, Any]]) -> None:
        """Send changes for this radiator, then refresh to reflect real state."""
        try:
            await self.coordinator.client.put_radiator_changes([self._radiator_id], cambios)
        except AtcCalaConnectionError as err:
            raise HomeAssistantError(f"Failed to update radiator: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._apply([(FIELD_ENCENDIDO, hvac_mode != HVACMode.OFF)])

    async def async_turn_on(self) -> None:
        await self._apply([(FIELD_ENCENDIDO, True)])

    async def async_turn_off(self) -> None:
        await self._apply([(FIELD_ENCENDIDO, False)])

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        radiator = self.radiator
        if preset_mode == PRESET_BOOST:
            temperature = (
                radiator.temp_forced
                if radiator and radiator.temp_forced is not None
                else radiator.target_temperature
                if radiator
                else MIN_TEMP
            )
            await self._start_boost(temperature or MIN_TEMP)
            return
        mode_letter = PRESET_TO_MODE.get(preset_mode)
        if mode_letter is None:
            raise ServiceValidationError(f"Unknown preset {preset_mode}")
        cambios: list[tuple[str, Any]] = [(FIELD_ENCENDIDO, True), (FIELD_MODE, mode_letter)]
        # Leaving Boost: clear the forced overlay.
        if radiator and radiator.boost_active:
            cambios.append((FIELD_MODO_FORZADO, False))
        await self._apply(cambios)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        radiator = self.radiator
        if radiator is None:
            raise HomeAssistantError("Radiator is unavailable")

        # Routes to the boost / Comfort / Eco setpoint (Eco is stored as an offset below
        # Comfort); Anti-frost and Programa have no settable setpoint.
        try:
            await self.coordinator.client.async_set_target_temperature(radiator, temperature)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        except AtcCalaConnectionError as err:
            raise HomeAssistantError(f"Failed to update radiator: {err}") from err
        await self.coordinator.async_request_refresh()

    async def _start_boost(self, temperature: float) -> None:
        minutes = self.coordinator.config_entry.options.get(
            CONF_BOOST_MINUTES, DEFAULT_BOOST_MINUTES
        )
        try:
            await self.coordinator.client.async_start_boost(
                self.coordinator.installation_id,
                [self._radiator_id],
                temperature,
                minutes,
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        except AtcCalaConnectionError as err:
            raise HomeAssistantError(f"Failed to start boost: {err}") from err
        await self.coordinator.async_request_refresh()
