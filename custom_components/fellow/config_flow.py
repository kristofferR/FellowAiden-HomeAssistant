"""Config flow for Fellow Aiden."""
from __future__ import annotations

import logging
from typing import Any, Mapping

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .fellow_aiden import (
    FellowAiden,
    FellowAuthError,
    FellowConnectionError,
    FellowNoSupportedDeviceError,
)
from .const import DOMAIN, DEFAULT_UPDATE_INTERVAL_MINUTES, MIN_UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required("email"): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
        vol.Required("password"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
)


async def _try_login(hass: HomeAssistant, email: str, password: str) -> None:
    """Attempt to authenticate asynchronously. Raises on failure."""
    session = async_get_clientsession(hass)
    api = FellowAiden(email, password, session)
    await api.authenticate()


def _login_error_key(err: Exception) -> str:
    """Map a login/setup exception to a config flow error key."""
    if isinstance(err, FellowAuthError):
        return "auth"
    if isinstance(err, FellowConnectionError):
        return "cannot_connect"
    if isinstance(err, FellowNoSupportedDeviceError):
        return "unsupported_device"
    return "unknown"


class FellowAidenConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fellow Aiden."""

    VERSION = 1

    _reauth_email: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input["email"]
            password = user_input["password"]
            try:
                await _try_login(self.hass, email, password)
            except Exception as err:
                errors["base"] = _login_error_key(err)
                if errors["base"] == "unknown":
                    _LOGGER.exception("Authentication failed")
                else:
                    _LOGGER.debug("Authentication failed: %s", err)
            else:
                await self.async_set_unique_id(email.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Fellow Aiden ({email})",
                    data={"email": email, "password": password},
                )

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    # -- Reauthentication ---------------------------------------------------

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle a reauth trigger (credentials expired)."""
        self._reauth_email = entry_data["email"]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user for a new password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input["password"]
            if self._reauth_email is None:
                return self.async_abort(reason="unknown")
            try:
                await _try_login(self.hass, self._reauth_email, password)
            except Exception as err:
                errors["base"] = _login_error_key(err)
                if errors["base"] == "unknown":
                    _LOGGER.exception("Re-authentication failed")
                else:
                    _LOGGER.debug("Re-authentication failed: %s", err)
            else:
                await self.async_set_unique_id(self._reauth_email.lower())
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={"password": password},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("password"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    # -- Reconfiguration ----------------------------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user update email and/or password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input["email"]
            password = user_input["password"]
            try:
                await _try_login(self.hass, email, password)
            except Exception as err:
                errors["base"] = _login_error_key(err)
                if errors["base"] == "unknown":
                    _LOGGER.exception("Reconfigure authentication failed")
                else:
                    _LOGGER.debug("Reconfigure authentication failed: %s", err)
            else:
                await self.async_set_unique_id(email.lower())
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates={"email": email, "password": password},
                )

        return self.async_show_form(
            step_id="reconfigure", data_schema=USER_SCHEMA, errors=errors
        )

    # -- Options flow -------------------------------------------------------

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> FellowAidenOptionsFlowHandler:
        return FellowAidenOptionsFlowHandler()


class FellowAidenOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options (polling interval)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            interval = user_input.get("update_interval_seconds")
            if interval is not None and interval < MIN_UPDATE_INTERVAL_SECONDS:
                errors["update_interval_seconds"] = "too_fast"
            else:
                return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            "update_interval_seconds", DEFAULT_UPDATE_INTERVAL_MINUTES * 60
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "update_interval_seconds",
                        default=current_interval,
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_UPDATE_INTERVAL_SECONDS, max=300),
                    ),
                }
            ),
            errors=errors,
            last_step=True,
        )
