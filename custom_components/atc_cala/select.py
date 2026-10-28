"""Select platform for ATC Cala: which schedule helper drives each radiator's schedule."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EVENT_STATE_CHANGED, EntityCategory
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AtcCalaConfigEntry, AtcCalaDataUpdateCoordinator
from .entity import AtcCalaEntity

SCHEDULE_DOMAIN = "schedule"
OPTION_NONE = "none"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtcCalaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a schedule helper select for every radiator."""
    coordinator = entry.runtime_data
    async_add_entities(
        AtcCalaScheduleHelperSelect(coordinator, radiator_id) for radiator_id in coordinator.data
    )


class AtcCalaScheduleHelperSelect(AtcCalaEntity, SelectEntity):
    """Links a schedule helper to the radiator; its blocks are synced as Comfort periods.

    The link is stored in the config entry options, so it survives restarts and the
    choice is the same however it was made.
    """

    _attr_translation_key = "schedule_helper"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AtcCalaDataUpdateCoordinator, radiator_id: str) -> None:
        super().__init__(coordinator, radiator_id)
        self._attr_unique_id = f"{radiator_id}_schedule_helper"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        # Keep the option list current as schedule helpers are added, removed or renamed.
        @callback
        def _is_schedule(event_data: EventStateChangedData) -> bool:
            return event_data["entity_id"].startswith(f"{SCHEDULE_DOMAIN}.")

        @callback
        def _schedule_changed(event: Event[EventStateChangedData]) -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_STATE_CHANGED, _schedule_changed, event_filter=_is_schedule
            )
        )

    def _helpers(self) -> dict[str, str]:
        """Option label -> schedule helper entity_id, by name (entity_id if names clash)."""
        states = sorted(
            self.hass.states.async_all(SCHEDULE_DOMAIN), key=lambda s: s.name.casefold()
        )
        names = [s.name for s in states]
        return {
            (s.name if names.count(s.name) == 1 else f"{s.name} ({s.entity_id})"): s.entity_id
            for s in states
        }

    @property
    def options(self) -> list[str]:
        return [OPTION_NONE, *self._helpers()]

    @property
    def current_option(self) -> str | None:
        linked = self.coordinator.schedule_helpers.get(self._radiator_id)
        if linked is None:
            return OPTION_NONE
        # None (unknown) if the linked helper no longer exists.
        return next((label for label, eid in self._helpers().items() if eid == linked), None)

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == OPTION_NONE else self._helpers()[option]
        self.coordinator.async_link_schedule_helper(self._radiator_id, entity_id)
