# ATC Cala — Home Assistant integration

A native Home Assistant integration for **ATC Cala** WiFi electric radiators (Grupo Ferroli
cloud). Adds a `climate` entity per radiator with target temperature, on/off, the four device
modes as presets, and the app's Manual mode, plus schedule and energy sensors. Everything is set up
through the UI; no MQTT or YAML is needed.

[![Open in the Home Assistant Marketplace](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=belamadar&repository=atc-cala-hass&category=integration)

It is built to [Home Assistant core standards](https://developers.home-assistant.io/docs/creating_component_index)
so it can be submitted upstream, but runs today as a custom component.

## Architecture

- **[`pyatccala`](https://gitlab.com/belamadar/pyatccala)** — a standalone async Python library that talks to the cloud API
  (OAuth login + token refresh, radiator polling, control). Home Assistant core requires
  device/cloud communication to live in a separate PyPI library; this is it.
- **`custom_components/atc_cala`** — this integration, which depends on `pyatccala`.

The reverse-engineered cloud protocol is documented in [`API.md`](API.md).

## Requirements

- An ATC Cala account (the same email/password you use in the ATC Cala mobile app).
- Home Assistant 2026.11 or newer.

## Installation

**From the Marketplace** (Home Assistant's built-in store for community integrations, cards and themes):

1. Click the **Open in the Home Assistant Marketplace** button above, or add
   `https://github.com/belamadar/atc-cala-hass` to the Marketplace as an **Integration**
   repository.
2. Install **ATC Cala** and restart Home Assistant.

Then go to **Settings → Devices & services → Add integration**, search for **ATC Cala**, and sign
in. Home Assistant installs the [`pyatccala`](https://pypi.org/project/pyatccala/) library from
PyPI automatically.

<!-- ha-marketplace:exclude-start -->
**Manually:** copy `custom_components/atc_cala` into your Home Assistant
`config/custom_components/` folder, restart Home Assistant, and add the integration as above.
<!-- ha-marketplace:exclude-end -->

## Configuration

Everything is configured through the UI:

- **Setup:** enter your ATC Cala email and password. The integration validates the login and
  discovers your installation automatically.
- **Options** (⚙️ on the integration): polling interval (default 60 s) and how long Manual mode
  lasts when it is started from the preset alone (default 24 hours).
- **Re-authentication:** if your password changes, Home Assistant prompts you to re-enter it.

## Entities

One `climate` entity per radiator:

| Feature | Source |
|---|---|
| Current temperature | `TempActual` |
| Target temperature | active mode's setpoint / Manual mode setpoint |
| HVAC mode | `Encendido` → `heat` / `off` |
| HVAC action | `Calentando` → `heating` / `idle` / `off` |
| Preset | Comfort / Eco / Anti-frost / Schedule / **Manual** |

Setting a temperature writes the setpoint that is in effect: the Manual setpoint in Manual mode,
otherwise Comfort or Eco (Eco is stored as an offset below Comfort). In the **Schedule** preset it
changes the setpoint of the current slot. Anti-frost is fixed at 7 °C.

**Manual** is the app's Manual mode (the suitcase icon): it holds a temperature until a date and
time, up to about a year ahead, then the radiator returns to its previous mode. A **Manual mode
until** `datetime` entity per radiator shows when it ends. Setting that entity starts Manual mode,
or moves its end if it is already on. Picking the Manual preset alone starts it for the default
duration from the options. Either way it uses the last Manual temperature, which you then change
with the climate entity's target temperature.

Two `sensor` entities per radiator describe its own weekly schedule: **Scheduled preset**
(Comfort/Eco right now) and **Next schedule change** (timestamp, with the upcoming preset as an
attribute). A **Schedule helper** `select` (under the device's Configuration) chooses which
schedule helper, if any, drives that schedule.

An **Energy today** sensor (kWh) per radiator reports the cloud's estimated consumption for the
day, the same figure the app shows under *Estimated consumption*. It resets at the installation's
midnight, and off-peak and peak kWh are attributes. Home Assistant's statistics keep the running
total across those resets, so add it to the Energy dashboard (Settings → Dashboards → Energy →
Individual devices) for an hourly, daily and monthly history.

The cloud reports no live power draw, only totals, and radiators seem to upload their usage every
few hours. Expect a few steps per day rather than a smooth curve, booked when the cloud receives
the data rather than when the radiator heated. The sensor is polled every 15 minutes.

More entity types (open-window, keypad lock, brightness, power limit) are planned as follow-ups; see [`API.md`](API.md) §11.

## Weekly schedule

The radiators run their weekly schedule themselves (48 half-hour Comfort/Eco slots per day), so it
keeps working when Home Assistant or the internet is down. To edit it from Home Assistant:

1. Create a **Schedule** helper (Settings → Devices & services → Helpers) and draw the Comfort
   periods. Everything outside the blocks is Eco.
2. On each radiator's device page, set **Schedule helper** (under Configuration) to that helper.
   Several radiators can share one helper; choosing **None** unlinks it and the radiator keeps
   its last schedule.

On every poll the integration compares each linked radiator's schedule with its helper and uploads
the days that differ, so edits apply within one polling interval (immediately when the helper's
state changes). Block times are rounded to the nearest half hour, and edits made in the ATC Cala
app to a linked radiator are overwritten. Put the radiator in the **Schedule** preset for it to
follow the program.

Automations can still override it — e.g. switch to Eco when everyone is away and back to Schedule
on return, or switch the Schedule helper select to a "Holiday" helper during school breaks; if Home
Assistant goes down the radiators simply keep following the weekly program.

## Removing the integration

Delete the integration from **Settings → Devices & services** (this removes its entities and
devices), then remove the `custom_components/atc_cala` folder and restart Home Assistant. No data
is stored outside the config entry.

<!-- ha-marketplace:exclude-start -->
## Development

```bash
python3.14 -m venv .venv && source .venv/bin/activate   # HA 2026.11 needs Python 3.14.2+
pip install -r requirements_test.txt ruff              # pytest-homeassistant + pyatccala
pip install -e ../pyatccala[test]                       # optional: a local library checkout

# Run the two test suites separately (they are separate projects):
(cd ../pyatccala && pytest -p no:homeassistant)          # library
pytest                                                   # integration (from this repo root)

ruff check custom_components/atc_cala
```

`pyatccala` and the integration are intentionally decoupled; the library has no Home Assistant
dependency and can be used on its own.
<!-- ha-marketplace:exclude-end -->

## Status

v0.1 — climate control, validated against real hardware. Roadmap toward a home-assistant/core
submission is tracked in `custom_components/atc_cala/quality_scale.yaml`.
