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

## Installation (custom component)

1. Copy `custom_components/atc_cala` into your Home Assistant `config/custom_components/` folder.
2. Install the library into Home Assistant's Python environment. It is pinned in the manifest as
   `pyatccala==0.1.0`; until it is published to PyPI, install it from source:
   ```bash
   pip install /path/to/pyatccala
   ```
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration**, search for **ATC Cala**, and sign in.

## Configuration

Everything is configured through the UI:

- **Setup:** enter your ATC Cala email and password. The integration validates the login and
  discovers your installation automatically.
- **Options** (⚙️ on the integration): polling interval (default 60 s) and default Boost duration
  (default 60 min).
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

Setting a temperature writes the current mode's stored setpoint (Comfort/Eco/Anti-frost). In the
**Schedule** preset the temperature follows the device's weekly program and is not directly
settable — switch to another preset or start **Boost**. Boost applies a timed override whose
expiry is computed from the cloud's own clock.

More entity types (energy sensors, open-window, keypad lock, brightness, power limit) are planned
as follow-ups; see [`API.md`](API.md) §11.

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
