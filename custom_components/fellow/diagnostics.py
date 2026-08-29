"""Diagnostics for Fellow Aiden."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import FellowAidenConfigEntry

TO_REDACT_CONFIG = {"email", "password", "brewer_id"}
TO_REDACT_DEVICE = {
    "id",
    "displayName",
    "serialNumber",
    "wifiMacAddress",
    "btMacAddress",
    "wifiSSID",
    "wifiSsid",
    "localIpAddress",
    "publicIpAddress",
    "hiddenProfiles",
    "profiles",
    "schedules",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FellowAidenConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data or {}

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT_CONFIG),
        "options": dict(entry.options),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
        },
        "device_config": async_redact_data(
            data.get("device_config", {}), TO_REDACT_DEVICE
        ),
        "profiles_count": len(data.get("profiles", [])),
        "schedules_count": len(data.get("schedules", [])),
        "brewer_name": async_redact_data(
            {"brewer_name": data.get("brewer_name")}, {"brewer_name"}
        )["brewer_name"],
    }
