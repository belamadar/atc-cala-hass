"""Constants for the ATC Cala integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "atc_cala"

# Config entry data / options keys
CONF_INSTALLATION_ID: Final = "installation_id"
CONF_INSTALLATION_NAME: Final = "installation_name"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_BOOST_MINUTES: Final = "boost_minutes"
#: Options: {IdRadiador: schedule helper entity_id} whose blocks are synced as Comfort.
CONF_SCHEDULE_HELPERS: Final = "schedule_helpers"

DEFAULT_POLL_INTERVAL: Final = 60  # seconds
DEFAULT_BOOST_MINUTES: Final = 60

MIN_POLL_INTERVAL: Final = 15
MAX_POLL_INTERVAL: Final = 3600

# Climate temperature bounds (°C). Conservative defaults; revisit vs device limits.
MIN_TEMP: Final = 5.0
MAX_TEMP: Final = 30.0
TEMP_STEP: Final = 0.5

# Don't re-upload an unchanged schedule more often than this while the cloud catches up.
SCHEDULE_RESYNC_INTERVAL: Final = timedelta(minutes=10)

DEFAULT_SCAN_INTERVAL: Final = timedelta(seconds=DEFAULT_POLL_INTERVAL)

MANUFACTURER: Final = "ATC / Grupo Ferroli"
MODEL: Final = "WiFi Radiator"

# HA preset names (shown in the UI) ↔ device mode letters (IdModoActual).
PRESET_COMFORT: Final = "comfort"
PRESET_ECO: Final = "eco"
PRESET_ANTIFROST: Final = "anti_frost"
PRESET_SCHEDULE: Final = "schedule"
PRESET_BOOST: Final = "boost"

# device mode letter -> preset
MODE_TO_PRESET: Final = {
    "C": PRESET_COMFORT,
    "E": PRESET_ECO,
    "A": PRESET_ANTIFROST,
    "P": PRESET_SCHEDULE,
}
# preset -> device mode letter (Boost is handled separately via ModoForzado)
PRESET_TO_MODE: Final = {v: k for k, v in MODE_TO_PRESET.items()}

PRESET_MODES: Final = [
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_ANTIFROST,
    PRESET_SCHEDULE,
    PRESET_BOOST,
]
