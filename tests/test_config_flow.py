"""Config flow tests for ATC Cala."""

from __future__ import annotations

from unittest.mock import AsyncMock

from pyatccala import AtcCalaAuthError, AtcCalaConnectionError

from custom_components.atc_cala.const import CONF_INSTALLATION_ID, DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


async def _start_user(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def test_user_flow_success(hass: HomeAssistant, patch_client):
    result = await _start_user(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "pw"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home"
    assert result["data"][CONF_INSTALLATION_ID] == 12345
    assert result["result"].unique_id == "10001"


async def test_invalid_auth(hass: HomeAssistant, patch_client):
    patch_client.login = AsyncMock(side_effect=AtcCalaAuthError("bad"))
    result = await _start_user(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "wrong"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_cannot_connect(hass: HomeAssistant, patch_client):
    patch_client.login = AsyncMock(side_effect=AtcCalaConnectionError("down"))
    result = await _start_user(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "pw"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_aborts(hass: HomeAssistant, patch_client, mock_entry):
    mock_entry.add_to_hass(hass)
    result = await _start_user(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "pw"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(hass: HomeAssistant, patch_client, mock_entry):
    mock_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": mock_entry.entry_id},
        data=mock_entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "newpw"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_entry.data[CONF_PASSWORD] == "newpw"

    # The successful reauth reloads the entry; let it finish and tear it down so the
    # coordinator's polling timer does not linger past the test.
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(mock_entry.entry_id)
    await hass.async_block_till_done()
