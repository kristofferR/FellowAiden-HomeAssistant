"""Coordinator to fetch data from the Fellow Aiden cloud."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .fellow_aiden import (
    FellowAiden,
    FellowAuthError,
    FellowConnectionError,
    FellowNoSupportedDeviceError,
)
from .brew_history import BrewHistoryManager
from .const import DEFAULT_UPDATE_INTERVAL_MINUTES

_LOGGER = logging.getLogger(__name__)

class FellowAidenDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch data from the Fellow Aiden cloud API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, email: str, password: str) -> None:
        """Initialize with credentials."""
        self.hass = hass
        self.email = email
        self.password = password
        self.api: FellowAiden | None = None
        self.history_manager = BrewHistoryManager(hass, entry.entry_id)
        self._next_refresh_verbose = False

        # Get update interval from options or use default
        update_interval_seconds = entry.options.get(
            "update_interval_seconds", DEFAULT_UPDATE_INTERVAL_MINUTES * 60
        )

        super().__init__(
            hass,
            _LOGGER,
            name="fellow_aiden_coordinator",
            update_interval=timedelta(seconds=update_interval_seconds),
            config_entry=entry,
        )

    async def async_config_entry_first_refresh(self) -> None:
        """Create the async API client and perform the initial refresh."""
        session = async_get_clientsession(self.hass)
        self.api = FellowAiden(self.email, self.password, session)
        try:
            await self.api.authenticate()
        except FellowAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed: {err}"
            ) from err
        except FellowConnectionError as err:
            raise ConfigEntryNotReady(
                f"Unable to connect to Fellow cloud: {err}"
            ) from err
        except FellowNoSupportedDeviceError as err:
            raise ConfigEntryError(str(err)) from err
        await super().async_config_entry_first_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the Fellow Aiden cloud API."""
        _LOGGER.debug("Starting data update cycle")
        if not self.api:
            _LOGGER.error("Fellow Aiden library not initialized")
            raise UpdateFailed("Fellow Aiden library not initialized")

        try:
            _LOGGER.debug("Fetching device data")
            await self.api.fetch_device()
        except FellowAuthError as err:
            raise ConfigEntryAuthFailed(  # noqa: TRY003
                f"Authentication failed: {err}"
            ) from err
        except FellowConnectionError as err:
            raise UpdateFailed(  # noqa: TRY003
                f"Device fetch failed: {err}"
            ) from err
        except FellowNoSupportedDeviceError as err:
            raise UpdateFailed(  # noqa: TRY003
                f"Device fetch failed: {err}"
            ) from err
        except Exception as err:
            raise UpdateFailed(  # noqa: TRY003
                f"Device fetch failed: {err}"
            ) from err

        brewer_name = self.api.get_display_name()
        try:
            profiles = await self.api.get_profiles()
            device_config = self.api.get_device_config()
            schedules = await self.api.get_schedules()
        except FellowAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed: {err}"
            ) from err
        except FellowConnectionError as err:
            raise UpdateFailed(  # noqa: TRY003
                f"Data fetch failed: {err}"
            ) from err
        except FellowNoSupportedDeviceError as err:
            raise UpdateFailed(  # noqa: TRY003
                f"Data fetch failed: {err}"
            ) from err
        except Exception as err:
            raise UpdateFailed(  # noqa: TRY003
                f"Data fetch failed: {err}"
            ) from err

        verbose_logging = self._next_refresh_verbose
        self._next_refresh_verbose = False

        if verbose_logging:
            _LOGGER.info("=== Fellow Aiden API Response ===")
            _LOGGER.info("Brewer name: %s", brewer_name)
            _LOGGER.info("Profiles (%d): %s", len(profiles) if profiles else 0, profiles)
            _LOGGER.info("Device config: %s", device_config)
            _LOGGER.info("Schedules (%d): %s", len(schedules) if schedules else 0, schedules)
            _LOGGER.info("=== End API Response ===")
        else:
            _LOGGER.debug(
                "Polled: %d profiles, %d schedules, device: %s",
                len(profiles) if profiles else 0,
                len(schedules) if schedules else 0,
                brewer_name,
            )

        if not brewer_name or not device_config:
            _LOGGER.error("Incomplete data fetched from Fellow Aiden.")
            raise UpdateFailed("Incomplete data fetched from Fellow Aiden.")

        result = {
            "brewer_name": brewer_name,
            "profiles": profiles,
            "device_config": device_config,
            "schedules": schedules,
        }
        _LOGGER.debug(
            "Returning data: %d profiles, %d schedules",
            len(profiles) if profiles else 0, len(schedules) if schedules else 0,
        )

        # Update historical data with the new data (non-fatal)
        _LOGGER.debug("Updating historical data")
        try:
            await self.history_manager.async_update_data(device_config, profiles)
        except Exception:
            _LOGGER.warning("Failed to update historical data", exc_info=True)

        _LOGGER.debug("Data update completed successfully")
        return result


    async def async_create_profile(self, profile_data: dict[str, Any]) -> None:
        """Create a new brew profile and refresh coordinator data."""
        if not self.api:
            raise RuntimeError("Fellow Aiden library not initialized")
        _LOGGER.debug("Creating profile with data: %s", profile_data)
        try:
            result = await self.api.create_profile(profile_data)
            if result is False:
                raise ValueError("Profile creation validation failed")
            _LOGGER.debug("Profile creation result: %s", result)
        except Exception:
            _LOGGER.exception("Profile creation failed")
            raise
        self._next_refresh_verbose = True
        await self.async_request_refresh()

    async def async_delete_profile(self, profile_id: str) -> None:
        """Delete a brew profile and refresh coordinator data."""
        if not self.api:
            raise RuntimeError("Fellow Aiden library not initialized")
        _LOGGER.debug("Deleting profile ID: %s", profile_id)
        try:
            result = await self.api.delete_profile_by_id(profile_id)
            if result is False:
                raise ValueError("Profile deletion failed")
            _LOGGER.debug("Profile deletion result: %s", result)
        except Exception:
            _LOGGER.exception("Profile deletion failed")
            raise
        self._next_refresh_verbose = True
        await self.async_request_refresh()

    async def async_create_schedule(self, schedule_data: dict[str, Any]) -> None:
        """Create a new brew schedule and refresh coordinator data."""
        if not self.api:
            raise RuntimeError("Fellow Aiden library not initialized")
        _LOGGER.debug("Creating schedule with data: %s", schedule_data)
        try:
            result = await self.api.create_schedule(schedule_data)
            if result is False:
                raise ValueError("Schedule creation validation failed")
            _LOGGER.debug("Schedule creation result: %s", result)
        except Exception:
            _LOGGER.exception("Schedule creation failed")
            raise
        self._next_refresh_verbose = True
        await self.async_request_refresh()

    async def async_delete_schedule(self, schedule_id: str) -> None:
        """Delete a brew schedule and refresh coordinator data."""
        if not self.api:
            raise RuntimeError("Fellow Aiden library not initialized")
        _LOGGER.debug("Deleting schedule ID: %s", schedule_id)
        try:
            result = await self.api.delete_schedule_by_id(schedule_id)
            if result is False:
                raise ValueError("Schedule deletion failed")
            _LOGGER.debug("Schedule deletion result: %s", result)
        except Exception:
            _LOGGER.exception("Schedule deletion failed")
            raise
        self._next_refresh_verbose = True
        await self.async_request_refresh()

    async def async_toggle_schedule(self, schedule_id: str, enabled: bool) -> None:
        """Enable or disable a brew schedule and refresh coordinator data."""
        if not self.api:
            raise RuntimeError("Fellow Aiden library not initialized")
        _LOGGER.debug("Toggling schedule ID: %s, enabled: %s", schedule_id, enabled)
        try:
            result = await self.api.toggle_schedule(schedule_id, enabled)
            if result is False:
                raise ValueError("Schedule toggle failed")
            _LOGGER.debug("Schedule toggle result: %s", result)
        except Exception:
            _LOGGER.exception("Schedule toggle failed")
            raise
        self._next_refresh_verbose = True
        await self.async_request_refresh()
