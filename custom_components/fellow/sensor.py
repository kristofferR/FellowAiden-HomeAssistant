import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength, UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .base_entity import FellowAidenBaseEntity
from .const import (
    MIN_HISTORICAL_DATA_FOR_ACCURACY,
    MIN_VALID_YEAR,
    TIMESTAMP_2024_01_01,
    FellowAidenConfigEntry,
)
from .coordinator import FellowAidenDataUpdateCoordinator
from .profile_resolution import profile_recipe_attributes, resolve_current_profile
from .schedule_helpers import (
    ScheduleOccurrence,
    next_schedule_occurrence,
    schedule_timezone,
)
from .telemetry import BREW_PHASES, brew_phase

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# Standard sensors: (api_key, translation_key, unit, device_class, state_class, entity_category, disabled_default)
STANDARD_SENSORS = [
    ("chimeVolume", "chime_volume", None, None, None, EntityCategory.DIAGNOSTIC, True),
    (
        "totalBrewingCycles",
        "total_brews",
        None,
        None,
        SensorStateClass.TOTAL_INCREASING,
        None,
        False,
    ),
    (
        "totalWaterVolumeL",
        "total_water_volume",
        UnitOfVolume.LITERS,
        SensorDeviceClass.VOLUME,
        SensorStateClass.TOTAL_INCREASING,
        None,
        False,
    ),
    (
        "brewingWaterVolumeMl",
        "last_brew_volume",
        UnitOfVolume.MILLILITERS,
        SensorDeviceClass.VOLUME,
        None,
        None,
        False,
    ),
    (
        "ibWaterQuantity",
        "instant_brew_water",
        UnitOfVolume.MILLILITERS,
        SensorDeviceClass.VOLUME,
        None,
        None,
        False,
    ),
    (
        "deviceTimezone",
        "device_timezone",
        None,
        None,
        None,
        EntityCategory.DIAGNOSTIC,
        True,
    ),
    (
        "elevation",
        "elevation",
        UnitOfLength.METERS,
        SensorDeviceClass.DISTANCE,
        None,
        EntityCategory.DIAGNOSTIC,
        True,
    ),
]

# Brew time sensors: (api_key, translation_key)
BREW_TIME_SENSORS = [
    ("brewEndTime", "last_brew_end_time"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FellowAidenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for the Fellow Aiden integration."""
    _LOGGER.debug("Setting up sensors for entry %s", entry.entry_id)
    coordinator = entry.runtime_data

    _LOGGER.debug("Coordinator data available: %s", coordinator.data is not None)
    if coordinator.data:
        _LOGGER.debug("Coordinator data keys: %s", list(coordinator.data.keys()))

    entities: list[SensorEntity] = []

    # Standard sensors from device config
    for (
        key,
        translation_key,
        unit,
        device_class,
        state_class,
        category,
        disabled,
    ) in STANDARD_SENSORS:
        entities.append(
            AidenSensor(
                coordinator=coordinator,
                entry=entry,
                key=key,
                translation_key=translation_key,
                unit=unit,
                device_class=device_class,
                state_class=state_class,
                entity_category=category,
                disabled_default=disabled,
            )
        )

    # Initialize derived sensor: Average Water per Brew
    entities.append(
        AidenAverageWaterPerBrewSensor(coordinator=coordinator, entry=entry)
    )

    # Brew time sensors
    for key, translation_key in BREW_TIME_SENSORS:
        entities.append(
            AidenBrewTimeSensor(
                coordinator=coordinator,
                entry=entry,
                key=key,
                translation_key=translation_key,
            )
        )

    # Analytics sensors
    entities.extend(
        [
            AidenAverageTimeBetweenBrewsSensor(coordinator, entry),
            AidenLastBrewTimeSensor(coordinator, entry),
            AidenLastBrewDurationSensor(coordinator, entry),
            AidenTotalWaterTodaySensor(coordinator, entry),
            AidenTotalWaterWeekSensor(coordinator, entry),
            AidenTotalWaterMonthSensor(coordinator, entry),
            AidenMostPopularProfileSensor(coordinator, entry),
            AidenCurrentProfileSensor(coordinator, entry),
            AidenBrewPhaseSensor(coordinator, entry),
            AidenConnectionTimestampSensor(coordinator, entry),
            AidenBasketSensor(coordinator, entry),
            AidenNextScheduledBrewSensor(coordinator, entry),
        ]
    )
    if coordinator.push_manager:
        entities.append(AidenLastCloudPushSensor(coordinator, entry))

    _LOGGER.debug("Adding %d sensor entities", len(entities))
    async_add_entities(entities, update_before_add=True)
    _LOGGER.info("Successfully set up %d sensors for Fellow Aiden", len(entities))


class AidenSensor(FellowAidenBaseEntity, SensorEntity):
    """Sensor for a value read directly from the device config."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
        key: str,
        translation_key: str,
        unit: str | None,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        entity_category: EntityCategory | None = None,
        disabled_default: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._key = key
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{entry.entry_id}-{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_entity_category = entity_category
        self._attr_entity_registry_enabled_default = not disabled_default

    @property
    def native_value(self) -> Any:
        """Retrieve and process the sensor's value."""
        data = self.coordinator.data
        if not data:
            return None
        device_config = data.get("device_config", {})
        value = device_config.get(self._key)

        # Apply unit conversion for water volume if applicable
        if self._key == "totalWaterVolumeL" and value is not None:
            return round(value / 1000.0, 2)  # API field is misnamed; value is in mL

        return value


class AidenLastCloudPushSensor(FellowAidenBaseEntity, SensorEntity):
    """Timestamp of the last Fellow FCM invalidation received by HA."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "last_cloud_push"

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}-last-cloud-push"

    @property
    def native_value(self) -> datetime | None:
        """Return the most recently received message timestamp."""
        manager = self.coordinator.push_manager
        return manager.last_message_at if manager else None

    @property
    def extra_state_attributes(self) -> dict[str, str | int]:
        """Expose receiver counters without tokens or Android credentials."""
        manager = self.coordinator.push_manager
        if manager is None:
            return {"status": "disabled"}
        return {
            "status": manager.status.value,
            "messages_received": manager.message_count,
            "reconnections": manager.reconnect_count,
        }


class AidenAverageWaterPerBrewSensor(FellowAidenBaseEntity, SensorEntity):
    """Average water usage per brew: totalWaterVolume / totalBrewingCycles."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_translation_key = "average_water_per_brew"
        self._attr_unique_id = f"{entry.entry_id}-avg_water_per_brew"
        self._attr_native_unit_of_measurement = UnitOfVolume.MILLILITERS
        self._attr_device_class = SensorDeviceClass.VOLUME

    @property
    def native_value(self) -> float | None:
        """Compute and return the average water volume per brew."""
        data = self.coordinator.data or {}
        device_config = data.get("device_config", {})
        total_water_ml = device_config.get("totalWaterVolumeL")
        total_brews = device_config.get("totalBrewingCycles")

        # Use explicit None checks - 0 is a valid value for total_water_ml
        if total_water_ml is None or total_brews is None or total_brews == 0:
            return None

        average_ml = total_water_ml / total_brews
        return round(average_ml)


class AidenBrewTimeSensor(FellowAidenBaseEntity, SensorEntity):
    """Displays a brew start or end time, converted from a Unix timestamp."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
        key: str,
        translation_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._key = key
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{entry.entry_id}-{key}"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Return the brew time as a timezone-aware datetime."""
        data = self.coordinator.data or {}
        device_config = data.get("device_config", {})
        timestamp_str = device_config.get(self._key)

        if not timestamp_str or timestamp_str == "0":
            return None

        try:
            timestamp_int = int(timestamp_str)
            if timestamp_int == 0:
                return None
            brew_datetime = dt_util.utc_from_timestamp(timestamp_int)
            if brew_datetime.year < MIN_VALID_YEAR:
                return None
            return brew_datetime
        except (ValueError, TypeError, OSError, OverflowError) as error:
            _LOGGER.error("Error parsing %s: %s", self._key, error)
            return None


class AidenAverageTimeBetweenBrewsSensor(FellowAidenBaseEntity, SensorEntity):
    """Rough estimate of average time between brews, from historical data."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_translation_key = "average_time_between_brews"
        self._attr_unique_id = f"{entry.entry_id}-avg_time_between_brews"
        self._attr_native_unit_of_measurement = UnitOfTime.HOURS
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float | None:
        """Calculate average time between brews using historical data."""
        return self.coordinator.history_manager.get_average_time_between_brews()

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        history_count = self.coordinator.history_manager.get_brew_history_count()
        return {
            "historical_brews": history_count,
            "accuracy": "High - based on actual historical data"
            if history_count >= MIN_HISTORICAL_DATA_FOR_ACCURACY
            else "Low - insufficient historical data",
            "note": f"Calculated from {history_count} recorded brews",
        }


class AidenLastBrewDurationSensor(FellowAidenBaseEntity, SensorEntity):
    """Duration of the latest brew cycle observed from start through completion."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = "last_brew_duration"
        self._attr_unique_id = f"{entry.entry_id}-last_brew_duration"
        self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
        self._attr_device_class = SensorDeviceClass.DURATION

    @property
    def native_value(self) -> int | None:
        """Return a trusted observed duration, never an unpaired API subtraction."""
        return self.coordinator.history_manager.get_last_brew_duration()


class AidenLastBrewTimeSensor(FellowAidenBaseEntity, SensorEntity):
    """When the last brew finished (timestamp)."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_translation_key = "last_brew_time"
        self._attr_unique_id = f"{entry.entry_id}-last_brew_time"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Return the last brew completion time using historical data."""
        # Try historical data first, fallback to device data
        historical_time = self.coordinator.history_manager.get_last_brew_time()
        if historical_time:
            # Ensure timezone is set
            if historical_time.tzinfo is None:
                return dt_util.as_local(historical_time)
            return historical_time

        # Fallback to device data
        data = self.coordinator.data
        if not data:
            return None
        device_config = data.get("device_config", {})
        end_time_str = device_config.get("brewEndTime")

        if not end_time_str or end_time_str == "0":
            return None

        try:
            timestamp_int = int(end_time_str)
            if (
                timestamp_int == 0 or timestamp_int < TIMESTAMP_2024_01_01
            ):  # Before 2024
                return None
            # Create timezone-aware datetime
            return dt_util.utc_from_timestamp(timestamp_int)
        except (ValueError, TypeError) as error:
            _LOGGER.error("Error parsing last brew time: %s", error)
            return None


class AidenTotalWaterTodaySensor(FellowAidenBaseEntity, SensorEntity):
    """Water used today, from historical tracking data."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_translation_key = "total_water_today"
        self._attr_unique_id = f"{entry.entry_id}-total_water_today"
        self._attr_native_unit_of_measurement = UnitOfVolume.LITERS
        self._attr_device_class = SensorDeviceClass.VOLUME
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> float | None:
        """Return total water used today using historical data."""
        # IMPORTANT: Only use historical tracking data, never fallback to device totals
        water_usage = self.coordinator.history_manager.get_water_usage_for_period(1)
        _LOGGER.debug("Water usage today from history: %s L", water_usage)

        # Ensure we never accidentally return device lifetime totals
        if water_usage is None or water_usage < 0:
            _LOGGER.warning(
                "Invalid water usage value from history manager, returning 0.0"
            )
            return 0.0

        return water_usage

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        water_records = self.coordinator.history_manager.get_water_usage_count()
        return {
            "historical_records": water_records,
            "accuracy": "High - based on actual usage tracking"
            if water_records > 0
            else "Low - no historical data yet",
            "note": f"Calculated from {water_records} water usage records",
        }


class AidenTotalWaterWeekSensor(FellowAidenBaseEntity, SensorEntity):
    """Water used this week, from historical tracking data."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_translation_key = "total_water_this_week"
        self._attr_unique_id = f"{entry.entry_id}-total_water_week"
        self._attr_native_unit_of_measurement = UnitOfVolume.LITERS
        self._attr_device_class = SensorDeviceClass.VOLUME
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> float | None:
        """Return total water used this week using historical data."""
        # IMPORTANT: Only use historical tracking data, never fallback to device totals
        water_usage = self.coordinator.history_manager.get_water_usage_for_period(7)
        _LOGGER.debug("Water usage this week from history: %s L", water_usage)

        # Ensure we never accidentally return device lifetime totals
        if water_usage is None or water_usage < 0:
            _LOGGER.warning(
                "Invalid water usage value from history manager, returning 0.0"
            )
            return 0.0

        return water_usage

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        water_records = self.coordinator.history_manager.get_water_usage_count()
        brew_count = self.coordinator.history_manager.get_brew_count_for_period(7)
        return {
            "historical_records": water_records,
            "brews_this_week": brew_count,
            "accuracy": "High - based on actual usage tracking"
            if water_records > 0
            else "Low - no historical data yet",
            "note": f"Calculated from {water_records} water usage records",
        }


class AidenTotalWaterMonthSensor(FellowAidenBaseEntity, SensorEntity):
    """Water used this month, from historical tracking data."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_translation_key = "total_water_this_month"
        self._attr_unique_id = f"{entry.entry_id}-total_water_month"
        self._attr_native_unit_of_measurement = UnitOfVolume.LITERS
        self._attr_device_class = SensorDeviceClass.VOLUME
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> float | None:
        """Return total water used this month using historical data."""
        # IMPORTANT: Only use historical tracking data, never fallback to device totals
        water_usage = self.coordinator.history_manager.get_water_usage_for_period(30)
        _LOGGER.debug("Water usage this month from history: %s L", water_usage)

        # Ensure we never accidentally return device lifetime totals
        if water_usage is None or water_usage < 0:
            _LOGGER.warning(
                "Invalid water usage value from history manager, returning 0.0"
            )
            return 0.0

        return water_usage

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        water_records = self.coordinator.history_manager.get_water_usage_count()
        brew_count = self.coordinator.history_manager.get_brew_count_for_period(30)
        return {
            "historical_records": water_records,
            "brews_this_month": brew_count,
            "accuracy": "High - based on actual usage tracking"
            if water_records > 0
            else "Low - no historical data yet",
            "note": f"Calculated from {water_records} water usage records",
        }


class AidenMostPopularProfileSensor(FellowAidenBaseEntity, SensorEntity):
    """Most-brewed profile, based on historical usage counts."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_translation_key = "most_popular_profile"
        self._attr_unique_id = f"{entry.entry_id}-most_popular_profile"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> str | None:
        """Return the most popular profile name using historical data."""
        # Try to get most popular from historical data
        most_popular = self.coordinator.history_manager.get_most_popular_profile()
        if most_popular:
            return most_popular

        # Fallback to default or first profile
        data = self.coordinator.data
        if not data or "profiles" not in data or not data["profiles"]:
            return "No profiles available"

        # Look for default profile first
        default_profile = next(
            (p for p in data["profiles"] if p.get("isDefaultProfile")), None
        )
        if default_profile:
            return default_profile.get("title", "Default Profile")

        # Otherwise return the first profile
        return data["profiles"][0].get("title", "Profile 1")

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        data = self.coordinator.data
        total_profiles = len(data.get("profiles", [])) if data else 0
        profile_stats = self.coordinator.history_manager.get_profile_usage_stats()
        most_popular = self.coordinator.history_manager.get_most_popular_profile()

        attrs = {
            "total_profiles": total_profiles,
            "profile_usage_stats": profile_stats,
        }

        if most_popular and profile_stats:
            attrs["accuracy"] = "High - based on actual usage tracking"
            attrs["note"] = f"Based on {sum(profile_stats.values())} recorded brews"
            attrs["usage_count"] = profile_stats.get(most_popular, 0)
        else:
            attrs["accuracy"] = "Low - using default/first profile"
            attrs["note"] = "No historical usage data available yet"

        return attrs


class AidenCurrentProfileSensor(FellowAidenBaseEntity, SensorEntity):
    """The currently selected or most recently used brew profile."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_translation_key = "current_profile"
        self._attr_unique_id = f"{entry.entry_id}-current_profile"

    def _detect_current_profile(self) -> tuple[str | None, str, str]:
        """Detect the current profile without side effects.

        Returns (profile_name, detection_method, confidence).
        Cached per coordinator data update to avoid duplicate computation.
        """
        data_id = id(self.coordinator.data)
        if getattr(self, "_cache_id", None) == data_id:
            return self._cache_result

        result = self._compute_current_profile()
        self._cache_id = data_id
        self._cache_result = result
        return result

    def _compute_current_profile(self) -> tuple[str | None, str, str]:
        """Run the actual detection logic."""
        data = self.coordinator.data or {}
        profiles = data.get("profiles", [])
        device_config = data.get("device_config", {})
        resolution = resolve_current_profile(profiles, device_config)
        if resolution.title is not None:
            return resolution.title, resolution.method, resolution.confidence

        most_popular = self.coordinator.history_manager.get_most_popular_profile()
        if most_popular:
            return most_popular, "historical_usage", "low_medium"

        return "No profiles available", "unknown", "low"

    @property
    def native_value(self) -> str | None:
        """Return the current profile name."""
        value, _, _ = self._detect_current_profile()
        return value

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        _, detection_method, confidence = self._detect_current_profile()
        data = self.coordinator.data
        total_profiles = len(data.get("profiles", [])) if data else 0

        last_used_time = None

        if data and "profiles" in data and data["profiles"]:
            # Get last used time for display
            profiles_with_last_used = []
            for profile in data["profiles"]:
                last_used = profile.get("lastUsedTime")
                if last_used and last_used != "0":
                    try:
                        last_used_timestamp = int(last_used)
                        if last_used_timestamp > 0:
                            profiles_with_last_used.append(
                                (profile, last_used_timestamp)
                            )
                    except (ValueError, TypeError):
                        continue

            if profiles_with_last_used:
                profiles_with_last_used.sort(key=lambda x: x[1], reverse=True)
                most_recent_timestamp = profiles_with_last_used[0][1]
                try:
                    last_used_dt = dt_util.as_local(
                        dt_util.utc_from_timestamp(most_recent_timestamp)
                    )
                    last_used_time = last_used_dt.isoformat()
                except (ValueError, OSError, OverflowError):
                    pass

        attrs = {
            "total_profiles": total_profiles,
            "detection_method": detection_method,
            "confidence": confidence,
        }

        if data:
            resolution = resolve_current_profile(
                data.get("profiles", []), data.get("device_config", {})
            )
            if resolution.profile:
                attrs.update(profile_recipe_attributes(resolution.profile))

        # Add last used time if available
        if last_used_time:
            attrs["last_used_time"] = last_used_time

        # Add last brew information if available
        last_brew_time = self.coordinator.history_manager.get_last_brew_time()
        if last_brew_time:
            attrs["last_brew_time"] = last_brew_time.isoformat()

        # Add profile usage stats
        profile_stats = self.coordinator.history_manager.get_profile_usage_stats()
        if profile_stats:
            attrs["profile_usage_stats"] = profile_stats
            attrs["total_historical_brews"] = sum(profile_stats.values())

        return attrs


class AidenBrewPhaseSensor(FellowAidenBaseEntity, SensorEntity):
    """Current v2 brew phase."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = "brew_phase"
        self._attr_unique_id = f"{entry.entry_id}-brew-phase"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = list(BREW_PHASES)

    @property
    def native_value(self) -> str:
        """Return the normalized current phase."""
        data = self.coordinator.data or {}
        return brew_phase(data.get("device_config", {}))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the raw state code for future protocol discoveries."""
        data = self.coordinator.data or {}
        state = data.get("device_config", {}).get("state")
        if not isinstance(state, dict) or not isinstance(state.get("value"), str):
            return {}
        return {"raw_phase": state["value"]}


class AidenNextScheduledBrewSensor(FellowAidenBaseEntity, SensorEntity):
    """Timestamp and recipe summary for the next enabled schedule."""

    _attr_translation_key = "next_scheduled_brew"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}-next-scheduled-brew"

    def _occurrence(self) -> ScheduleOccurrence | None:
        data = self.coordinator.data or {}
        timezone = schedule_timezone(
            data.get("device_config", {}), self.coordinator.hass.config.time_zone
        )
        return next_schedule_occurrence(
            data.get("schedules", []),
            data.get("profiles", []),
            dt_util.now(),
            timezone,
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the next scheduled brew time."""
        occurrence = self._occurrence()
        return occurrence.start if occurrence else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the schedule details useful to automations."""
        data = self.coordinator.data or {}
        schedules = data.get("schedules", [])
        attrs: dict[str, Any] = {
            "enabled_schedules": sum(
                schedule.get("enabled") is True for schedule in schedules
            )
        }
        occurrence = self._occurrence()
        if occurrence:
            attrs.update(
                {
                    "profile": occurrence.profile_title,
                    "water_ml": occurrence.water_ml,
                    "repeat_days": list(occurrence.repeat_days),
                }
            )
        return attrs


class AidenConnectionTimestampSensor(FellowAidenBaseEntity, SensorEntity):
    """Last cloud connection time reported by the brewer."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = "cloud_connection_time"
        self._attr_unique_id = f"{entry.entry_id}-connection-timestamp"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> datetime | None:
        """Convert the API's millisecond Unix timestamp to UTC."""
        data = self.coordinator.data or {}
        raw_value = data.get("device_config", {}).get("connectionTimestamp")
        try:
            timestamp = int(raw_value)
        except (TypeError, ValueError):
            return None
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
            value = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
        return value if value.year >= MIN_VALID_YEAR else None


class AidenBasketSensor(FellowAidenBaseEntity, SensorEntity):
    """Which basket is inserted: single serve, batch brew, or missing."""

    def __init__(
        self, coordinator: FellowAidenDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_translation_key = "basket"
        self._attr_unique_id = f"{entry.entry_id}-basket"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        device_config = data.get("device_config", {})
        single_basket = device_config.get("singleBrewBasketPresent", False)
        batch_basket = device_config.get("batchBrewBasketPresent", False)

        if single_basket:
            return "Single Serve"
        if batch_basket:
            return "Batch Brew"
        return "Missing"
