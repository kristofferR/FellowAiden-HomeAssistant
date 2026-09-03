"""Constants for Fellow Aiden."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import FellowAidenDataUpdateCoordinator

type FellowAidenConfigEntry = ConfigEntry[FellowAidenDataUpdateCoordinator]

DOMAIN = "fellow"
PLATFORMS = ["sensor", "binary_sensor", "calendar", "button"]

# Update intervals. Push keeps idle state current, while short polling bursts
# provide responsive phase changes during and immediately after activity.
DEFAULT_UPDATE_INTERVAL_SECONDS = 30
MIN_UPDATE_INTERVAL_SECONDS = 10
ACTIVE_UPDATE_INTERVAL_SECONDS = 10
PUSH_CONNECTED_IDLE_UPDATE_INTERVAL_SECONDS = 60
RECENT_ACTIVITY_SECONDS = 120
RESOURCE_UPDATE_INTERVAL_SECONDS = 5 * 60
DEFAULT_ENABLE_CLOUD_PUSH = True
CONF_ENABLE_CLOUD_PUSH = "enable_cloud_push"
CONF_UPDATE_INTERVAL_SECONDS = "update_interval_seconds"
LEGACY_CONF_UPDATE_INTERVAL_MINUTES = "update_interval_minutes"
EVENT_CLOUD_PUSH = "fellow_cloud_push"
EVENT_DEVICE = "fellow_device_event"
PUSH_MANAGERS = "push_managers"


def get_update_interval_seconds(options: Mapping[str, Any]) -> int:
    """Return the configured interval, preserving the version 1 minute option."""
    seconds = options.get(CONF_UPDATE_INTERVAL_SECONDS)
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
        return int(seconds)
    minutes = options.get(LEGACY_CONF_UPDATE_INTERVAL_MINUTES)
    if isinstance(minutes, (int, float)) and not isinstance(minutes, bool):
        return int(minutes * 60)
    return DEFAULT_UPDATE_INTERVAL_SECONDS


def get_adaptive_update_interval_seconds(
    configured_interval_seconds: int,
    *,
    push_connected: bool,
    recently_active: bool,
) -> int:
    """Return the current live-state polling interval."""
    if recently_active:
        return ACTIVE_UPDATE_INTERVAL_SECONDS
    if push_connected:
        return PUSH_CONNECTED_IDLE_UPDATE_INTERVAL_SECONDS
    return configured_interval_seconds


# Historical data constants
HISTORY_RETENTION_DAYS = 365
MIN_VALID_YEAR = 2023

# Water amount limits (from Fellow API)
MIN_WATER_AMOUNT_ML = 150
MAX_WATER_AMOUNT_ML = 1500

# Data validation thresholds
MIN_HISTORICAL_DATA_FOR_ACCURACY = 2

# Profile defaults
DEFAULT_PROFILE_TYPE = 0
