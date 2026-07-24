"""Fellow Aiden integration for Home Assistant."""
from __future__ import annotations

import json
import logging
import re
from datetime import time
from typing import cast

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.typing import ConfigType

from .const import DEFAULT_PROFILE_TYPE, DOMAIN, PLATFORMS, FellowAidenConfigEntry
from .coordinator import FellowAidenDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PROFILE_ID_RE = re.compile(r"^(p|plocal)\d+$")
_CAMEL_TO_SNAKE_RE = re.compile(r"([a-z0-9])([A-Z])")


def _normalize_keys(data: dict) -> dict:
    """Normalize camelCase keys to snake_case for backward compatibility.

    Allows automations written for v1.2 (camelCase keys) to keep working
    after the v1.3 switch to snake_case service parameters.
    """
    return {_CAMEL_TO_SNAKE_RE.sub(r"\1_\2", k).lower(): v for k, v in data.items()}

REFRESH_RESPONSE_REDACT_KEYS = {
    "email",
    "password",
    "id",
    "wifiMacAddress",
    "btMacAddress",
    "wifiSSID",
    "localIpAddress",
}


def _coerce_temperature_list(value: object) -> list[float]:
    """Coerce profile pulse temperatures to a list of floats.

    Accepts:
    - JSON array string, e.g. "[96, 97, 98]"
    - Comma-separated string, e.g. "96,97,98"
    - Native list/tuple values
    """
    raw_items: list[object]

    if isinstance(value, (list, tuple)):
        raw_items = list(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise vol.Invalid("Temperature list cannot be empty")

        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise vol.Invalid("Invalid JSON temperature list") from exc
            if not isinstance(parsed, list):
                raise vol.Invalid("Temperature JSON must be a list")
            raw_items = parsed
        else:
            raw_items = [item.strip() for item in stripped.split(",")]
    else:
        raise vol.Invalid("Temperature value must be a list or string")

    if not raw_items:
        raise vol.Invalid("Temperature list cannot be empty")

    temperatures: list[float] = []
    for item in raw_items:
        if item == "":
            raise vol.Invalid("Temperature list contains empty values")
        if isinstance(item, bool) or not isinstance(item, (str, int, float)):
            raise vol.Invalid(f"Invalid temperature value: {item}")
        try:
            temperatures.append(float(item))
        except (TypeError, ValueError) as exc:
            raise vol.Invalid(f"Invalid temperature value: {item}") from exc

    return temperatures

CREATE_PROFILE_SCHEMA = vol.All(_normalize_keys, vol.Schema({
    vol.Optional("config_entry_id"): cv.string,
    vol.Optional("profile_type", default=DEFAULT_PROFILE_TYPE): vol.Coerce(int),
    vol.Required("title"): cv.string,
    vol.Required("ratio"): vol.Coerce(float),
    vol.Required("bloom_enabled"): cv.boolean,
    vol.Required("bloom_ratio"): vol.Coerce(float),
    vol.Required("bloom_duration"): vol.Coerce(int),
    vol.Required("bloom_temperature"): vol.Coerce(int),
    vol.Required("ss_pulses_enabled"): cv.boolean,
    vol.Required("ss_pulses_number"): vol.Coerce(int),
    vol.Required("ss_pulses_interval"): vol.Coerce(int),
    vol.Required("ss_pulse_temperatures"): _coerce_temperature_list,
    vol.Required("batch_pulses_enabled"): cv.boolean,
    vol.Required("batch_pulses_number"): vol.Coerce(int),
    vol.Required("batch_pulses_interval"): vol.Coerce(int),
    vol.Required("batch_pulse_temperatures"): _coerce_temperature_list,
}))

CREATE_SCHEDULE_SCHEMA = vol.All(_normalize_keys, vol.Schema({
    vol.Optional("config_entry_id"): cv.string,
    vol.Optional("monday", default=False): cv.boolean,
    vol.Optional("tuesday", default=False): cv.boolean,
    vol.Optional("wednesday", default=False): cv.boolean,
    vol.Optional("thursday", default=False): cv.boolean,
    vol.Optional("friday", default=False): cv.boolean,
    vol.Optional("saturday", default=False): cv.boolean,
    vol.Optional("sunday", default=False): cv.boolean,
    vol.Required("time"): cv.string,
    vol.Required("amount_of_water"): vol.Coerce(int),
    vol.Optional("profile_name"): cv.string,
    vol.Optional("profile_id"): cv.string,
    vol.Optional("enabled", default=True): cv.boolean,
}))


def _get_coordinator(
    hass: HomeAssistant, config_entry_id: str | None = None
) -> FellowAidenDataUpdateCoordinator:
    """Return the coordinator selected for a service call."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_integrations",
        )

    loaded_entries = [
        cast(FellowAidenConfigEntry, entry)
        for entry in entries
        if entry.state is ConfigEntryState.LOADED
    ]
    if not loaded_entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_loaded",
        )

    if config_entry_id:
        target = next(
            (
                entry
                for entry in loaded_entries
                if entry.entry_id == config_entry_id
            ),
            None,
        )
        if target is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="target_not_loaded",
                translation_placeholders={"config_entry_id": config_entry_id},
            )
        return target.runtime_data

    if len(loaded_entries) > 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="target_required",
        )

    return loaded_entries[0].runtime_data


def _profile_id_by_name(
    coordinator: FellowAidenDataUpdateCoordinator, name: str
) -> str | None:
    """Look up a profile ID by its title. Returns None if not found."""
    data = coordinator.data
    if not data or "profiles" not in data:
        return None
    for profile in data["profiles"]:
        if profile.get("title") == name:
            return profile.get("id")
    return None


def _available_profile_names(
    coordinator: FellowAidenDataUpdateCoordinator,
) -> list[str]:
    data = coordinator.data
    if not data or "profiles" not in data:
        return []
    return [p.get("title", f"Profile {i}") for i, p in enumerate(data["profiles"])]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register Fellow Aiden services."""

    async def handle_create_profile(call: ServiceCall) -> None:
        coordinator = _get_coordinator(
            hass, call.data.get("config_entry_id")
        )
        data = {
            "profileType": call.data.get("profile_type", DEFAULT_PROFILE_TYPE),
            "title": call.data["title"],
            "ratio": call.data["ratio"],
            "bloomEnabled": call.data["bloom_enabled"],
            "bloomRatio": call.data["bloom_ratio"],
            "bloomDuration": call.data["bloom_duration"],
            "bloomTemperature": call.data["bloom_temperature"],
            "ssPulsesEnabled": call.data["ss_pulses_enabled"],
            "ssPulsesNumber": call.data["ss_pulses_number"],
            "ssPulsesInterval": call.data["ss_pulses_interval"],
            "ssPulseTemperatures": call.data["ss_pulse_temperatures"],
            "batchPulsesEnabled": call.data["batch_pulses_enabled"],
            "batchPulsesNumber": call.data["batch_pulses_number"],
            "batchPulsesInterval": call.data["batch_pulses_interval"],
            "batchPulseTemperatures": call.data["batch_pulse_temperatures"],
        }
        try:
            await coordinator.async_create_profile(data)
        except ValueError as exc:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="create_profile_failed",
                translation_placeholders={"error": str(exc)},
            ) from exc
        except Exception as exc:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="create_profile_failed",
                translation_placeholders={"error": str(exc)},
            ) from exc

    async def handle_delete_profile(call: ServiceCall) -> None:
        coordinator = _get_coordinator(
            hass, call.data.get("config_entry_id")
        )
        pid = call.data.get("profile_id")
        if not pid:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="profile_id_required",
            )
        try:
            await coordinator.async_delete_profile(pid)
        except Exception as exc:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="delete_profile_failed",
                translation_placeholders={"error": str(exc)},
            ) from exc

    async def handle_list_profiles(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(
            hass, call.data.get("config_entry_id")
        )
        data = coordinator.data
        if not data or "profiles" not in data or not data["profiles"]:
            return {"profiles": []}
        return {
            "profiles": [
                {
                    "id": p.get("id"),
                    "title": p.get("title", "Unnamed Profile"),
                    "isDefault": p.get("isDefaultProfile", False),
                }
                for p in data["profiles"]
            ]
        }

    async def handle_get_profile_details(call: ServiceCall) -> ServiceResponse:
        profile_input = call.data.get("profile_name") or call.data.get("profile_id")
        if not profile_input:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="provide_profile_id_or_name",
            )

        coordinator = _get_coordinator(
            hass, call.data.get("config_entry_id")
        )
        data = coordinator.data
        if not data or "profiles" not in data:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_profiles",
            )

        target = next(
            (
                p
                for p in data["profiles"]
                if p.get("title") == profile_input or p.get("id") == profile_input
            ),
            None,
        )
        if not target:
            names = [p.get("title", "Unnamed") for p in data["profiles"]]
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="profile_not_found",
                translation_placeholders={
                    "profile": profile_input,
                    "available": ", ".join(names),
                },
            )
        return {"profile": target}

    async def handle_create_schedule(call: ServiceCall) -> None:
        coordinator = _get_coordinator(
            hass, call.data.get("config_entry_id")
        )
        profile_input = call.data.get("profile_name") or call.data.get("profile_id")
        if not profile_input:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="provide_schedule_profile",
            )

        profile_id = _profile_id_by_name(coordinator, profile_input)
        if not profile_id:
            if PROFILE_ID_RE.match(profile_input):
                profile_id = profile_input
            else:
                names = _available_profile_names(coordinator)
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="profile_not_found",
                    translation_placeholders={
                        "profile": profile_input,
                        "available": ", ".join(names),
                    },
                )

        time_str: str | None = call.data.get("time")
        if not time_str:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="time_required",
            )
        try:
            time_obj = time.fromisoformat(time_str)
        except ValueError as exc:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="bad_time_format",
                translation_placeholders={"time_str": time_str},
            ) from exc

        seconds = time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second
        schedule_data = {
            "days": [
                call.data.get("sunday", False),
                call.data.get("monday", False),
                call.data.get("tuesday", False),
                call.data.get("wednesday", False),
                call.data.get("thursday", False),
                call.data.get("friday", False),
                call.data.get("saturday", False),
            ],
            "secondFromStartOfTheDay": seconds,
            "enabled": call.data.get("enabled", True),
            "amountOfWater": call.data["amount_of_water"],
            "profileId": profile_id,
        }
        try:
            await coordinator.async_create_schedule(schedule_data)
        except ValueError as exc:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="create_schedule_failed",
                translation_placeholders={"error": str(exc)},
            ) from exc
        except Exception as exc:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="create_schedule_failed",
                translation_placeholders={"error": str(exc)},
            ) from exc

    async def handle_delete_schedule(call: ServiceCall) -> None:
        coordinator = _get_coordinator(
            hass, call.data.get("config_entry_id")
        )
        sid = call.data.get("schedule_id")
        if not sid:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="schedule_id_required",
            )
        try:
            await coordinator.async_delete_schedule(sid)
        except Exception as exc:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="delete_schedule_failed",
                translation_placeholders={"error": str(exc)},
            ) from exc

    async def handle_toggle_schedule(call: ServiceCall) -> None:
        coordinator = _get_coordinator(
            hass, call.data.get("config_entry_id")
        )
        sid = call.data.get("schedule_id")
        if not sid:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="schedule_id_required",
            )
        enabled = call.data.get("enabled", True)
        try:
            await coordinator.async_toggle_schedule(sid, enabled)
        except Exception as exc:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="toggle_schedule_failed",
                translation_placeholders={"error": str(exc)},
            ) from exc

    async def handle_list_schedules(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(
            hass, call.data.get("config_entry_id")
        )
        await coordinator.async_request_refresh()
        data = coordinator.data
        schedules = data.get("schedules", []) if data else []
        return {"schedules": schedules}

    async def handle_debug_water_usage(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(
            hass, call.data.get("config_entry_id")
        )
        device_config = (coordinator.data or {}).get("device_config", {})
        return {
            "water_usage_record_count": coordinator.history_manager.get_water_usage_count(),
            "current_device_total_ml": device_config.get("totalWaterVolumeL", 0),
            "water_usage_today_l": coordinator.history_manager.get_water_usage_for_period(1),
            "water_usage_week_l": coordinator.history_manager.get_water_usage_for_period(7),
            "water_usage_month_l": coordinator.history_manager.get_water_usage_for_period(30),
        }

    async def handle_reset_water_tracking(call: ServiceCall) -> None:
        coordinator = _get_coordinator(
            hass, call.data.get("config_entry_id")
        )
        device_config = (coordinator.data or {}).get("device_config", {})
        current_total = device_config.get("totalWaterVolumeL", 0)
        _LOGGER.info(
            "Resetting water tracking baseline to %d ml (%.2f L)",
            current_total,
            current_total / 1000.0,
        )
        try:
            await coordinator.history_manager.async_reset_water_tracking(current_total)
        except Exception as exc:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="reset_water_failed",
                translation_placeholders={"error": str(exc)},
            ) from exc

    async def handle_refresh_and_log_data(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(
            hass, call.data.get("config_entry_id")
        )
        coordinator._next_refresh_verbose = True
        await coordinator.async_request_refresh()
        data = coordinator.data
        if not data:
            return {"error": "No data available after refresh"}
        return async_redact_data(data, REFRESH_RESPONSE_REDACT_KEYS)

    hass.services.async_register(
        DOMAIN, "create_profile", handle_create_profile, schema=CREATE_PROFILE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "delete_profile", handle_delete_profile, schema=None
    )
    hass.services.async_register(
        DOMAIN,
        "list_profiles",
        handle_list_profiles,
        schema=None,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "get_profile_details",
        handle_get_profile_details,
        schema=None,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "create_schedule", handle_create_schedule, schema=CREATE_SCHEDULE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "delete_schedule", handle_delete_schedule, schema=None
    )
    hass.services.async_register(
        DOMAIN, "toggle_schedule", handle_toggle_schedule, schema=None
    )
    hass.services.async_register(
        DOMAIN,
        "list_schedules",
        handle_list_schedules,
        schema=None,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "debug_water_usage",
        handle_debug_water_usage,
        schema=None,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "reset_water_tracking", handle_reset_water_tracking, schema=None
    )
    hass.services.async_register(
        DOMAIN,
        "refresh_and_log_data",
        handle_refresh_and_log_data,
        schema=None,
        supports_response=SupportsResponse.ONLY,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: FellowAidenConfigEntry) -> bool:
    """Set up Fellow Aiden from a config entry."""
    coordinator = FellowAidenDataUpdateCoordinator(
        hass,
        entry,
        entry.data["email"],
        entry.data["password"],
        entry.data.get("brewer_id"),
    )
    await coordinator.async_config_entry_first_refresh()

    # Version 1 entries were keyed by account email. Persist the selected
    # physical brewer so subsequent entries on the same account can choose a
    # different Aiden and every poll remains pinned to the same device.
    if "brewer_id" not in entry.data and coordinator.api:
        brewer_id = coordinator.api.get_brewer_id()
        if brewer_id:
            hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, "brewer_id": brewer_id},
                unique_id=brewer_id,
            )

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FellowAidenConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(
    hass: HomeAssistant, entry: FellowAidenConfigEntry
) -> bool:
    """Migrate account-level entries to the per-brewer config format."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        hass.config_entries.async_update_entry(entry, version=2)
    return True


async def _async_update_options(hass: HomeAssistant, entry: FellowAidenConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
