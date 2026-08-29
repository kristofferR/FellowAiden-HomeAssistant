"""Config flow for Fellow Aiden."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import DEFAULT_UPDATE_INTERVAL_SECONDS, DOMAIN, MIN_UPDATE_INTERVAL_SECONDS
from .fellow_aiden import (
    FellowAiden,
    FellowAuthError,
    FellowConnectionError,
    FellowNoSupportedDeviceError,
)

_LOGGER = logging.getLogger(__name__)


def _time_zone(hass: HomeAssistant) -> str:
    """Return Home Assistant's IANA timezone for the v2 login payload."""
    config = getattr(hass, "config", None)
    return getattr(config, "time_zone", None) or "UTC"


USER_SCHEMA = vol.Schema(
    {
        vol.Required("email"): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL)
        ),
        vol.Required("password"): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


async def _try_login(
    hass: HomeAssistant, email: str, password: str
) -> list[dict[str, Any]]:
    """Authenticate and return every supported brewer on the account."""
    session = async_get_clientsession(hass)
    api = FellowAiden(email, password, session, timezone=_time_zone(hass))
    await api.authenticate(fetch_device=False)
    return await api.get_supported_devices()


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

    VERSION = 2

    _reauth_email: str | None = None
    _reauth_brewer_id: str | None = None
    _email: str | None = None
    _password: str | None = None
    _available_devices: list[dict[str, Any]] | None = None

    def _configured_brewer_ids(self) -> set[str]:
        """Return brewer IDs already represented by config entries."""
        brewer_ids: set[str] = set()
        for entry in self._async_current_entries():
            brewer_id = entry.data.get("brewer_id")
            if not brewer_id:
                runtime_data = getattr(entry, "runtime_data", None)
                api = getattr(runtime_data, "api", None)
                brewer_id = api.get_brewer_id() if api else None
            if (
                not brewer_id
                and self._email
                and self._available_devices
                and entry.data.get("email", "").lower() == self._email.lower()
            ):
                # A not-yet-loaded version 1 entry has no persisted brewer ID.
                # It used the first compatible device, so reserve that device
                # until setup can migrate the entry.
                brewer_id = self._available_devices[0].get("id")
            if isinstance(brewer_id, str):
                brewer_ids.add(brewer_id)
        return brewer_ids

    @staticmethod
    def _device_name(device: Mapping[str, Any]) -> str:
        """Return a useful display name for a discovered brewer."""
        display_name = device.get("displayName")
        if isinstance(display_name, str) and display_name:
            return display_name
        return f"Fellow Aiden ({device.get('id', 'unknown')})"

    async def _async_create_device_entry(
        self, device: dict[str, Any]
    ) -> ConfigFlowResult:
        """Create a config entry for one physical brewer."""
        if self._email is None or self._password is None:
            return self.async_abort(reason="unknown")

        brewer_id = device.get("id")
        if not isinstance(brewer_id, str):
            return self.async_abort(reason="unknown")
        await self.async_set_unique_id(brewer_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._device_name(device),
            data={
                "email": self._email,
                "password": self._password,
                "brewer_id": brewer_id,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input["email"]
            password = user_input["password"]
            try:
                devices = await _try_login(self.hass, email, password)
            except Exception as err:
                errors["base"] = _login_error_key(err)
                if errors["base"] == "unknown":
                    _LOGGER.exception("Authentication failed")
                else:
                    _LOGGER.debug("Authentication failed: %s", err)
            else:
                self._email = email
                self._password = password
                self._available_devices = devices
                configured_ids = self._configured_brewer_ids()
                available_devices = [
                    device
                    for device in devices
                    if device.get("id") not in configured_ids
                ]
                if not available_devices:
                    return self.async_abort(reason="all_brewers_configured")

                self._available_devices = available_devices
                if len(available_devices) == 1:
                    return await self._async_create_device_entry(available_devices[0])
                return await self.async_step_device()

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose which unconfigured brewer to add."""
        if not self._available_devices:
            return self.async_abort(reason="unknown")

        devices_by_id: dict[str, dict[str, Any]] = {}
        for device in self._available_devices:
            brewer_id = device.get("id")
            if isinstance(brewer_id, str):
                devices_by_id[brewer_id] = device
        if user_input is not None:
            selected_device = devices_by_id.get(user_input["brewer_id"])
            if selected_device is None:
                return self.async_abort(reason="unknown")
            return await self._async_create_device_entry(selected_device)

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required("brewer_id"): vol.In(
                        {
                            brewer_id: self._device_name(device)
                            for brewer_id, device in devices_by_id.items()
                        }
                    )
                }
            ),
        )

    # -- Reauthentication ---------------------------------------------------

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle a reauth trigger (credentials expired)."""
        self._reauth_email = entry_data["email"]
        self._reauth_brewer_id = entry_data.get("brewer_id")
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
                devices = await _try_login(self.hass, self._reauth_email, password)
                if self._reauth_brewer_id and not any(
                    device.get("id") == self._reauth_brewer_id for device in devices
                ):
                    raise FellowNoSupportedDeviceError(
                        "The configured brewer is not available on this account."
                    )
            except Exception as err:
                errors["base"] = _login_error_key(err)
                if errors["base"] == "unknown":
                    _LOGGER.exception("Re-authentication failed")
                else:
                    _LOGGER.debug("Re-authentication failed: %s", err)
            else:
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
            entry = self._get_reconfigure_entry()
            brewer_id = entry.data.get("brewer_id")
            try:
                devices = await _try_login(self.hass, email, password)
                if brewer_id and not any(
                    device.get("id") == brewer_id for device in devices
                ):
                    raise FellowNoSupportedDeviceError(
                        "The configured brewer is not available on this account."
                    )
            except Exception as err:
                errors["base"] = _login_error_key(err)
                if errors["base"] == "unknown":
                    _LOGGER.exception("Reconfigure authentication failed")
                else:
                    _LOGGER.debug("Reconfigure authentication failed: %s", err)
            else:
                if not brewer_id:
                    # A migrated entry that has not persisted its brewer yet is
                    # still keyed by account email, so keep the original
                    # account check as a fallback. Without it, reconfigure
                    # would accept any Fellow account and silently retarget
                    # the entry at a different physical brewer.
                    await self.async_set_unique_id(email.lower())
                    self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry,
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
            "update_interval_seconds", DEFAULT_UPDATE_INTERVAL_SECONDS
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
