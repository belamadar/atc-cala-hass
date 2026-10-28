"""Fixtures for ATC Cala integration tests: a fake pyatccala client + HA config entry."""

from __future__ import annotations

import time
from copy import deepcopy
from unittest.mock import patch

import pytest
from pyatccala import AtcCalaClient, Installation, Radiator
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.atc_cala.const import (
    CONF_INSTALLATION_ID,
    CONF_INSTALLATION_NAME,
    DOMAIN,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.util import dt as dt_util

INSTALLATION_PAYLOAD = {
    "datos": {
        "IdInstalacion": 12345,
        "Nombre": "Home",
        "tipoInstalacion": "WIFI",
        "Moneda": "€",
    },
    "nzonas": 0,
    "nradiadores": 2,
}

RADIATOR_PAYLOAD = {
    "IdRadiador": "000C01234567890",
    "IdGateway": "000C01234567890",
    "IdZona": 0,
    "Nombre": "Living room",
    "TempActual": 20.6,
    "IdModoActual": "C",
    "TempComfort": 21.0,
    "TempEco": 3.0,  # offset below Comfort
    "TempAntiFrost": 7.0,
    "TempForzado": 22.0,
    "TemperaturaConsignaCalculada": 21.0,
    "TiempoForzado": "0",
    "ModoForzado": False,
    "Encendido": True,
    "Calentando": True,
    "TecladoBloqueado": False,
    "VentanasAbiertas": False,
    "VentanasAbiertasStatus": False,
    "Brillo": 0,
    "Potencia": 1800,
    "LimitePotencia": 100,
    "Software": "V 1.16.25",
    "Tipo": "WIFI",
    "Err_Offline": False,
    "ProgramacionL": "E" * 48,
}


class FakeClient:
    """Stand-in for pyatccala.AtcCalaClient used across the integration."""

    def __init__(self, *args, **kwargs) -> None:
        self.user_info = {"idUser": "10001"}
        self._radiator = deepcopy(RADIATOR_PAYLOAD)
        self.put_calls: list[tuple[list[str], list[tuple[str, str]]]] = []
        self.boost_calls: list[tuple] = []

    async def login(self):
        return {"access_token": "t"}

    async def async_ensure_token(self):
        return None

    async def get_installations(self):
        return [Installation.from_dict(deepcopy(INSTALLATION_PAYLOAD))]

    async def get_radiators(self, installation_id, id_zone=0):
        # HoraActual is the installation's local "now"; use HA's clock (same timezone).
        self._radiator["HoraActual"] = dt_util.now().replace(tzinfo=None).isoformat()
        return [Radiator.from_dict(deepcopy(self._radiator))]

    async def put_radiator_changes(self, heaters, cambios, zones=None):
        # Record and apply to the in-memory radiator so a refresh reflects the change.
        # Serialize exactly like the real client so tests verify end-to-end encoding.
        from pyatccala.client import _to_str

        norm = [(c, _to_str(v)) for c, v in cambios]
        self.put_calls.append((heaters, norm))
        for campo, valor in cambios:
            self._radiator[campo] = valor
        return {"traza": "COUNT: 1"}

    async def async_start_boost(self, installation_id, heaters, temperature, minutes):
        self.boost_calls.append((installation_id, heaters, temperature, minutes))
        self._radiator["ModoForzado"] = True
        self._radiator["TempForzado"] = temperature
        self._radiator["TiempoForzado"] = str(int(time.time()) + minutes * 60)
        return {"traza": "COUNT: 1"}

    # Real setpoint routing/validation, recorded through put_radiator_changes above.
    async_set_target_temperature = AtcCalaClient.async_set_target_temperature
    async_set_comfort_temperature = AtcCalaClient.async_set_comfort_temperature
    async_set_eco_temperature = AtcCalaClient.async_set_eco_temperature
    async_set_eco_offset = AtcCalaClient.async_set_eco_offset
    async_set_boost_temperature = AtcCalaClient.async_set_boost_temperature
    async_set_schedule = AtcCalaClient.async_set_schedule

    async def close(self):
        return None


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture(autouse=True)
def patch_client(fake_client: FakeClient):
    """Patch AtcCalaClient everywhere the integration constructs it."""
    with (
        patch("custom_components.atc_cala.AtcCalaClient", return_value=fake_client),
        patch(
            "custom_components.atc_cala.config_flow.AtcCalaClient",
            return_value=fake_client,
        ),
    ):
        yield fake_client


@pytest.fixture
def mock_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="10001",
        title="Home",
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "pw",
            CONF_INSTALLATION_ID: 12345,
            CONF_INSTALLATION_NAME: "Home",
        },
    )
