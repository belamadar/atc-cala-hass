"""Config flow for ATC Cala."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from pyatccala import AtcCalaAuthError, AtcCalaClient, AtcCalaConnectionError

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_BOOST_MINUTES,
    CONF_INSTALLATION_ID,
    CONF_INSTALLATION_NAME,
    CONF_POLL_INTERVAL,
    DEFAULT_BOOST_MINUTES,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)
from .coordinator import AtcCalaConfigEntry

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
)


class AtcCalaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the ATC Cala config flow."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: credentials → validate → create entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, info = await self._validate(user_input)
            if not errors:
                await self.async_set_unique_id(info["account_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info["installation_name"],
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_INSTALLATION_ID: info["installation_id"],
                        CONF_INSTALLATION_NAME: info["installation_name"],
                    },
                )
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when the token can no longer be renewed."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            candidate = {
                CONF_USERNAME: reauth_entry.data[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            errors, _info = await self._validate(candidate)
            if not errors:
                return self.async_update_reload_and_abort(
                    reauth_entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={CONF_USERNAME: reauth_entry.data[CONF_USERNAME]},
        )

    async def _validate(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Try to log in and fetch the first installation. Returns (errors, info)."""
        client = AtcCalaClient(
            user_input[CONF_USERNAME],
            user_input[CONF_PASSWORD],
            session=async_get_clientsession(self.hass),
        )
        try:
            await client.login()
            installations = await client.get_installations()
        except AtcCalaAuthError:
            return {"base": "invalid_auth"}, {}
        except AtcCalaConnectionError:
            return {"base": "cannot_connect"}, {}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error validating ATC Cala credentials")
            return {"base": "unknown"}, {}

        if not installations:
            return {"base": "no_installations"}, {}

        installation = installations[0]
        account_id = str(client.user_info.get("idUser") or user_input[CONF_USERNAME])
        return {}, {
            "account_id": account_id,
            "installation_id": installation.id_installation,
            "installation_name": installation.name or "ATC Cala",
        }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: AtcCalaConfigEntry) -> "AtcCalaOptionsFlow":
        return AtcCalaOptionsFlow()


class AtcCalaOptionsFlow(OptionsFlow):
    """Options: poll interval and boost duration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_POLL_INTERVAL,
                    default=options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): vol.All(cv.positive_int, vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL)),
                vol.Optional(
                    CONF_BOOST_MINUTES,
                    default=options.get(CONF_BOOST_MINUTES, DEFAULT_BOOST_MINUTES),
                ): vol.All(cv.positive_int, vol.Range(min=5, max=1440)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
