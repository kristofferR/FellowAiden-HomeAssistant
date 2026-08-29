"""Constants for Fellow Aiden."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import FellowAidenDataUpdateCoordinator

type FellowAidenConfigEntry = ConfigEntry[FellowAidenDataUpdateCoordinator]

DOMAIN = "fellow"
PLATFORMS = ["sensor", "select", "binary_sensor"]

# Update intervals. Device state changes quickly during a brew, while profiles
# and schedules are configuration data and can be refreshed less frequently.
DEFAULT_UPDATE_INTERVAL_SECONDS = 10
MIN_UPDATE_INTERVAL_SECONDS = 10
RESOURCE_UPDATE_INTERVAL_SECONDS = 60
PUSH_CONNECTED_POLL_INTERVAL_SECONDS = 60
DEFAULT_ENABLE_CLOUD_PUSH = True
CONF_ENABLE_CLOUD_PUSH = "enable_cloud_push"
EVENT_CLOUD_PUSH = "fellow_cloud_push"
PUSH_MANAGERS = "push_managers"


# Historical data constants
HISTORY_RETENTION_DAYS = 365
TIMESTAMP_2024_01_01 = 1704067201  # Used for timestamp validation
MIN_VALID_YEAR = 2023

# Water amount limits (from Fellow API)
MIN_WATER_AMOUNT_ML = 150
MAX_WATER_AMOUNT_ML = 1500

# Data validation thresholds
MIN_HISTORICAL_DATA_FOR_ACCURACY = 2

# Profile defaults
DEFAULT_PROFILE_TYPE = 0
