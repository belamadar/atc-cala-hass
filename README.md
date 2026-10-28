# ATC Cala — Home Assistant integration

A native Home Assistant integration for **ATC Cala** WiFi electric radiators (Grupo Ferroli
cloud). Adds a `climate` entity per radiator with target temperature, on/off, the four device
modes as presets, and a timed Boost — set up entirely through the UI, no MQTT and no HACS.

It is built to [Home Assistant core standards](https://developers.home-assistant.io/docs/creating_component_index)
so it can be submitted upstream, but runs today as a custom component.

## Architecture

- **[`pyatccala`](../pyatccala)** — a standalone async Python library that talks to the cloud API
  (OAuth login + token refresh, radiator polling, control). Home Assistant core requires
  device/cloud communication to live in a separate PyPI library; this is it.
- **`custom_components/atc_cala`** — this integration, which depends on `pyatccala`.

The reverse-engineered cloud protocol is documented in [`API.md`](API.md).

## Requirements

- An ATC Cala account (the same email/password you use in the ATC Cala mobile app).
- Home Assistant 2026.7 or newer.

## Installation

Development happens on [GitLab](https://gitlab.com/belamadar/atc-cala-hass); a read-only mirror on
GitHub exists only so HACS can install it.

**With HACS:** HACS → ⋮ → **Custom repositories** → add
`https://github.com/belamadar/atc-cala-hass` as type **Integration**, install **ATC Cala**, and
restart Home Assistant.

**Manually:** copy `custom_components/atc_cala` into your Home Assistant
`config/custom_components/` folder and restart Home Assistant.

Either way, Home Assistant installs the [`pyatccala`](https://pypi.org/project/pyatccala/) library
from PyPI automatically. Then go to **Settings → Devices & services → Add integration**, search for
**ATC Cala**, and sign in.

## Configuration

Everything is configured through the UI:

- **Setup:** enter your ATC Cala email and password. The integration validates the login and
  discovers your installation automatically.
- **Options** (⚙️ on the integration): polling interval (default 60 s), default Boost duration
  (default 60 min) and an optional **schedule helper** per radiator (see below).
- **Re-authentication:** if your password changes, Home Assistant prompts you to re-enter it.

## Entities

One `climate` entity per radiator:

| Feature | Source |
|---|---|
| Current temperature | `TempActual` |
| Target temperature | active mode's setpoint / boost setpoint |
| HVAC mode | `Encendido` → `heat` / `off` |
| HVAC action | `Calentando` → `heating` / `idle` / `off` |
| Preset | Comfort / Eco / Anti-frost / Schedule / **Boost** |

Setting a temperature writes the setpoint that is in effect: the boost setpoint during a boost,
otherwise Comfort or Eco (Eco is stored as an offset below Comfort). In the **Schedule** preset it
changes the setpoint of the current slot. Anti-frost is fixed at 7 °C. Boost applies a timed
override whose expiry is computed from the cloud's own clock.

Two `sensor` entities per radiator describe its own weekly schedule: **Scheduled preset**
(Comfort/Eco right now) and **Next schedule change** (timestamp, with the upcoming preset as an
attribute).

More entity types (energy sensors, open-window, keypad lock, brightness, power limit) are planned
as follow-ups; see [`API.md`](API.md) §11.

## Weekly schedule

The radiators run their weekly schedule themselves (48 half-hour Comfort/Eco slots per day), so it
keeps working when Home Assistant or the internet is down. To edit it from Home Assistant:

1. Create a **Schedule** helper (Settings → Devices & services → Helpers) and draw the Comfort
   periods. Everything outside the blocks is Eco.
2. In the integration's options, pick that helper for one or more radiators.

On every poll the integration compares each linked radiator's schedule with its helper and uploads
the days that differ, so edits apply within one polling interval (immediately when the helper's
state changes). Block times are rounded to the nearest half hour, and edits made in the ATC Cala
app to a linked radiator are overwritten. Put the radiator in the **Schedule** preset for it to
follow the program.

Automations can still override it — e.g. switch to Eco when everyone is away and back to Schedule
on return; if Home Assistant goes down the radiators simply keep following the weekly program.

## Removing the integration

Delete the integration from **Settings → Devices & services** (this removes its entities and
devices), then remove the `custom_components/atc_cala` folder and restart Home Assistant. No data
is stored outside the config entry.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ../pyatccala[test]                       # the library + its test deps
pip install pytest-homeassistant-custom-component ruff   # the integration test harness

# Run the two test suites separately (they are separate projects):
(cd ../pyatccala && pytest -p no:homeassistant)          # library
pytest                                                   # integration (from this repo root)

ruff check custom_components/atc_cala
```

`pyatccala` and the integration are intentionally decoupled; the library has no Home Assistant
dependency and can be used on its own.

## Status

v0.1 — climate control, validated against real hardware. Roadmap toward a home-assistant/core
submission is tracked in `custom_components/atc_cala/quality_scale.yaml`.
