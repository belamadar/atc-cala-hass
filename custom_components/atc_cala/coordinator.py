"""Data update coordinator for ATC Cala."""

from __future__ import annotations

import logging
from time import monotonic
from datetime import datetime, time, timedelta

from pyatccala import (
    SCHEDULE_DAYS,
    AtcCalaAuthError,
    AtcCalaClient,
    AtcCalaConnectionError,
    Radiator,
    is_slot_aligned,
    slots_from_ranges,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_POLL_INTERVAL,
    CONF_SCHEDULE_HELPERS,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    SCHEDULE_RESYNC_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type AtcCalaConfigEntry = ConfigEntry["AtcCalaDataUpdateCoordinator"]

# Schedule helper weekday keys, in the same Monday-first order as SCHEDULE_DAYS.
_HELPER_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class AtcCalaDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Radiator]]):
    """Polls the ATC Cala cloud and exposes radiators keyed by IdRadiador.

    After each poll it also reconciles radiators linked to a schedule helper: if the
    radiator's weekly schedule differs from the helper's, the differing days are uploaded.
    """

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
        #: Installation local time minus UTC, measured from the last poll.
        self.local_offset: timedelta | None = None
        # radiator id -> (uploaded week, monotonic time) to avoid re-uploading while the
        # cloud catches up; helpers we've already warned about.
        self._uploaded: dict[str, tuple[dict[str, str], float]] = {}
        self._warned: set[str] = set()

    @property
    def schedule_helpers(self) -> dict[str, str]:
        """Linked schedule helpers: {IdRadiador: entity_id}."""
        return self.config_entry.options.get(CONF_SCHEDULE_HELPERS, {})

    async def _async_update_data(self) -> dict[str, Radiator]:
        try:
            await self.client.async_ensure_token()
            radiators = await self.client.get_radiators(self.installation_id)
        except AtcCalaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AtcCalaConnectionError as err:
            raise UpdateFailed(str(err)) from err
        data = {r.id_radiator: r for r in radiators}
        self._update_local_offset(radiators)
        await self._async_sync_schedules(data)
        return data

    # -- installation clock --------------------------------------------------------

    def _update_local_offset(self, radiators: list[Radiator]) -> None:
        device_time = next((r.device_time for r in radiators if r.device_time), None)
        if device_time is None:
            return
        utc_now = dt_util.utcnow().replace(tzinfo=None)
        minutes = round((device_time - utc_now).total_seconds() / 900) * 15
        self.local_offset = timedelta(minutes=minutes)
        ha_offset = dt_util.now().utcoffset()
        if ha_offset is not None and ha_offset != self.local_offset:
            self._warn_once(
                "timezone",
                "The installation's clock (UTC%s) differs from Home Assistant's timezone "
                "(UTC%s); schedule helper times are applied in the installation's time",
                _fmt_offset(self.local_offset),
                _fmt_offset(ha_offset),
            )

    def installation_now(self) -> datetime | None:
        """The installation's current local wall time (naive)."""
        if self.local_offset is None:
            return None
        return dt_util.utcnow().replace(tzinfo=None) + self.local_offset

    def installation_to_utc(self, local: datetime) -> datetime | None:
        """Convert a naive installation-local time to an aware UTC datetime."""
        if self.local_offset is None:
            return None
        return (local - self.local_offset).replace(tzinfo=dt_util.UTC)

    # -- schedule helper sync ------------------------------------------------------

    async def _async_sync_schedules(self, radiators: dict[str, Radiator]) -> None:
        for radiator_id, helper in self.schedule_helpers.items():
            radiator = radiators.get(radiator_id)
            if radiator is None or radiator.offline:
                continue
            week = await self._async_helper_week(helper)
            if week is None:
                continue
            changed = {day: slots for day, slots in week.items() if radiator.schedule.get(day) != slots}
            if not changed:
                self._uploaded.pop(radiator_id, None)
                continue
            previous = self._uploaded.get(radiator_id)
            if (
                previous is not None
                and previous[0] == week
                and monotonic() - previous[1]
                < SCHEDULE_RESYNC_INTERVAL.total_seconds()
            ):
                continue  # already uploaded; give the cloud time to apply it
            try:
                await self.client.async_set_schedule(radiator_id, changed)
            except (AtcCalaAuthError, AtcCalaConnectionError, ValueError) as err:
                _LOGGER.warning("Failed to sync %s to %s: %s", helper, radiator.name, err)
                continue
            self._uploaded[radiator_id] = (week, monotonic())
            _LOGGER.info(
                "Synced schedule helper %s to radiator %s (%s)",
                helper,
                radiator.name,
                ", ".join(changed),
            )

    async def _async_helper_week(self, entity_id: str) -> dict[str, str] | None:
        """The helper's blocks as {day letter: 48-slot string}, or None if unavailable."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state == STATE_UNAVAILABLE:
            self._warn_once(entity_id, "Schedule helper %s is not available", entity_id)
            return None
        try:
            response = await self.hass.services.async_call(
                "schedule",
                "get_schedule",
                {"entity_id": entity_id},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            self._warn_once(entity_id, "Could not read schedule helper %s: %s", entity_id, err)
            return None
        blocks = (response or {}).get(entity_id, {})
        week: dict[str, str] = {}
        for helper_day, day in zip(_HELPER_DAYS, SCHEDULE_DAYS, strict=True):
            ranges = [
                (_as_time(block["from"]), _as_time(block["to"]))
                for block in blocks.get(helper_day, [])
            ]
            if any(not is_slot_aligned(t) for r in ranges for t in r):
                self._warn_once(
                    f"{entity_id}:align",
                    "Schedule helper %s has times that are not on the half hour; the "
                    "radiators work in 30-minute slots, so they are rounded",
                    entity_id,
                )
            week[day] = slots_from_ranges(ranges)
        self._warned.discard(entity_id)
        return week

    def _warn_once(self, key: str, msg: str, *args: object) -> None:
        if key not in self._warned:
            self._warned.add(key)
            _LOGGER.warning(msg, *args)


def _as_time(value: time | str) -> time:
    if isinstance(value, time):
        return value
    return time.max if value.startswith("24:") else time.fromisoformat(value)


def _fmt_offset(offset: timedelta) -> str:
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"
