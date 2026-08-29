"""Brew history data management for Fellow Aiden integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import storage
from homeassistant.util import dt as dt_util

from .const import HISTORY_RETENTION_DAYS, MIN_HISTORICAL_DATA_FOR_ACCURACY
from .profile_resolution import resolve_current_profile

_LOGGER = logging.getLogger(__name__)


class BrewHistoryManager:
    """Manages historical brew data storage and calculations using async file operations."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the brew history manager."""
        self.hass = hass
        self.entry_id = entry_id
        self._store = storage.Store(hass, 1, f"fellow_aiden_history_{entry_id}")
        self._brew_history: list[dict[str, Any]] = []
        self._water_usage_history: list[dict[str, Any]] = []
        self._profile_usage: dict[str, int] = {}
        self._last_total_brews = 0
        self._last_total_water = 0
        self._tracking_initialized = False
        self._data_loaded = False

    async def async_load_history(self) -> None:
        """Load historical data from storage."""
        try:
            data = await self._store.async_load()
            if data is not None:
                self._brew_history = data.get("brew_history", [])
                self._water_usage_history = data.get("water_usage_history", [])
                self._profile_usage = data.get("profile_usage", {})
                self._last_total_brews = data.get("last_total_brews", 0)
                self._last_total_water = data.get("last_total_water", 0)
                # Stored data from older releases already has a valid baseline,
                # even though it predates the explicit initialization flag.
                self._tracking_initialized = data.get("tracking_initialized", True)
                _LOGGER.debug(
                    "Loaded brew history: %d brews, %d water records",
                    len(self._brew_history),
                    len(self._water_usage_history),
                )
            self._data_loaded = True
        except Exception as e:  # noqa: BLE001 - storage failures are non-fatal
            _LOGGER.error("Failed to load brew history: %s", e)
            self._brew_history = []
            self._water_usage_history = []
            self._profile_usage = {}
            self._tracking_initialized = False
            self._data_loaded = True

    async def _async_save_history(self) -> None:
        """Save historical data to storage."""
        if not self._data_loaded:
            return

        try:
            data = {
                "brew_history": self._brew_history,
                "water_usage_history": self._water_usage_history,
                "profile_usage": self._profile_usage,
                "last_total_brews": self._last_total_brews,
                "last_total_water": self._last_total_water,
                "tracking_initialized": self._tracking_initialized,
                "last_updated": dt_util.now().isoformat(),
            }
            await self._store.async_save(data)
            _LOGGER.debug("Saved brew history")
        except Exception as e:  # noqa: BLE001 - storage failures are non-fatal
            _LOGGER.error("Failed to save brew history: %s", e)

    async def async_update_data(
        self, device_config: dict[str, Any], profiles: list[dict[str, Any]]
    ) -> None:
        """Update historical data with new device information."""
        # Ensure data is loaded first
        if not self._data_loaded:
            await self.async_load_history()

        current_total_brews = device_config.get("totalBrewingCycles", 0)
        current_total_water = device_config.get("totalWaterVolumeL", 0)
        brew_start_time = device_config.get("brewStartTime")
        brew_end_time = device_config.get("brewEndTime")

        now = dt_util.now()
        data_changed = False

        # Zero is a valid counter value. An explicit flag prevents the first
        # brew after a zero baseline from being mistaken for initialization.
        if not self._tracking_initialized:
            _LOGGER.info(
                "Initializing water usage tracking baseline: %s brews, %s ml water",
                current_total_brews,
                current_total_water,
            )
            self._last_total_brews = current_total_brews
            self._last_total_water = current_total_water
            self._tracking_initialized = True
            await self._async_save_history()
            return

        # A factory reset or server counter reset starts a new baseline. Never
        # turn the reset into a negative usage record.
        if current_total_brews < self._last_total_brews:
            self._last_total_brews = current_total_brews
            data_changed = True
        if current_total_water < self._last_total_water:
            self._last_total_water = current_total_water
            data_changed = True

        # Check if we have a new brew
        if current_total_brews > self._last_total_brews:
            new_brews = current_total_brews - self._last_total_brews
            _LOGGER.info("Detected %d new brew(s)", new_brews)

            # Add brew record(s)
            for i in range(new_brews):
                brew_record = {
                    "timestamp": now.isoformat(),
                    "total_brews_at_time": current_total_brews - (new_brews - 1 - i),
                    "total_water_at_time": current_total_water,
                }

                # Add timing information if available
                if brew_start_time and brew_end_time:
                    try:
                        start_ts = int(brew_start_time)
                        end_ts = int(brew_end_time)
                        if start_ts > 0 and end_ts > 0 and start_ts < end_ts:
                            start_dt = dt_util.as_local(
                                dt_util.utc_from_timestamp(start_ts)
                            )
                            end_dt = dt_util.as_local(
                                dt_util.utc_from_timestamp(end_ts)
                            )
                            brew_record["start_time"] = start_dt.isoformat()
                            brew_record["end_time"] = end_dt.isoformat()
                            brew_record["duration_seconds"] = end_ts - start_ts
                    except (ValueError, TypeError):
                        pass

                if profiles:
                    resolved_profile = resolve_current_profile(
                        profiles, device_config
                    ).profile
                    if resolved_profile:
                        profile_id = resolved_profile.get("id")
                        profile_title = resolved_profile.get("title", "Unknown Profile")
                        brew_record["profile_id"] = profile_id
                        brew_record["profile_title"] = profile_title

                        # Update profile usage counter
                        if profile_title in self._profile_usage:
                            self._profile_usage[profile_title] += 1
                        else:
                            self._profile_usage[profile_title] = 1

                self._brew_history.append(brew_record)

            self._last_total_brews = current_total_brews
            data_changed = True

        # Check if water usage changed
        if current_total_water > self._last_total_water:
            water_used = current_total_water - self._last_total_water
            water_record = {
                "timestamp": now.isoformat(),
                "water_used_ml": water_used,
                "total_water_at_time": current_total_water,
            }
            self._water_usage_history.append(water_record)
            self._last_total_water = current_total_water
            _LOGGER.debug("Recorded water usage: %s ml", water_used)
            data_changed = True

        if data_changed:
            # Clean old records based on retention policy
            cutoff_date = now - timedelta(days=HISTORY_RETENTION_DAYS)
            self._clean_old_records(cutoff_date)

            # Save updated history
            await self._async_save_history()

    def _clean_old_records(self, cutoff_date: datetime) -> None:
        """Remove records older than cutoff date."""
        original_brew_count = len(self._brew_history)
        original_water_count = len(self._water_usage_history)

        def is_record_recent(record: dict) -> bool:
            """Check if a record is more recent than cutoff_date."""
            timestamp_str = record.get("timestamp", "")
            if not timestamp_str:
                return False
            try:
                record_dt = datetime.fromisoformat(timestamp_str)
                # Ensure timezone awareness for comparison
                if record_dt.tzinfo is None:
                    record_dt = dt_util.as_local(record_dt)
                return record_dt > cutoff_date
            except (ValueError, TypeError):
                _LOGGER.debug("Failed to parse timestamp: %s", timestamp_str)
                return False

        self._brew_history = [
            record for record in self._brew_history if is_record_recent(record)
        ]

        self._water_usage_history = [
            record for record in self._water_usage_history if is_record_recent(record)
        ]

        if (
            len(self._brew_history) < original_brew_count
            or len(self._water_usage_history) < original_water_count
        ):
            _LOGGER.debug(
                "Cleaned old records: %d->%d brews, %d->%d water",
                original_brew_count,
                len(self._brew_history),
                original_water_count,
                len(self._water_usage_history),
            )

    def get_average_time_between_brews(self) -> float | None:
        """Calculate average time between brews in hours."""
        if len(self._brew_history) < MIN_HISTORICAL_DATA_FOR_ACCURACY:
            return None

        # Get timestamps of brews
        timestamps = []
        for record in self._brew_history:
            try:
                ts = datetime.fromisoformat(record["timestamp"])
                # Ensure timezone awareness for comparison
                if ts.tzinfo is None:
                    ts = dt_util.as_local(ts)
                timestamps.append(ts)
            except (ValueError, KeyError):
                continue

        if len(timestamps) < MIN_HISTORICAL_DATA_FOR_ACCURACY:
            return None

        # Sort timestamps
        timestamps.sort()

        # Calculate intervals
        intervals = []
        for i in range(1, len(timestamps)):
            interval = (
                timestamps[i] - timestamps[i - 1]
            ).total_seconds() / 3600  # Convert to hours
            if interval > 0:  # Ignore negative or zero intervals
                intervals.append(interval)

        if intervals:
            return round(sum(intervals) / len(intervals), 1)

        return None

    def get_water_usage_for_period(self, days: int) -> float:
        """Get total water usage for the specified number of days."""
        if not self._water_usage_history:
            _LOGGER.debug("No water usage history available for %d-day period", days)
            return 0.0

        cutoff_date = dt_util.now() - timedelta(days=days)

        total_water = 0.0
        matching_records = 0
        for record in self._water_usage_history:
            timestamp_str = record.get("timestamp", "")
            if timestamp_str:
                try:
                    record_dt = datetime.fromisoformat(timestamp_str)
                    if record_dt.tzinfo is None:
                        record_dt = dt_util.as_local(record_dt)
                    if record_dt > cutoff_date:
                        water_used = record.get("water_used_ml", 0)
                        total_water += water_used
                        matching_records += 1
                        _LOGGER.debug(
                            "Found water usage record: %dml on %s",
                            water_used,
                            timestamp_str,
                        )
                except (ValueError, TypeError):
                    continue

        total_liters = round(total_water / 1000.0, 2)
        _LOGGER.debug(
            "Water usage for %d-day period: %d records, %dml (%sL)",
            days,
            matching_records,
            total_water,
            total_liters,
        )
        return total_liters

    def get_average_brew_duration(self) -> float | None:
        """Calculate average brew duration in minutes."""
        durations = []

        for record in self._brew_history:
            duration = record.get("duration_seconds")
            if duration and duration > 0:
                durations.append(duration / 60.0)  # Convert to minutes

        if durations:
            return round(sum(durations) / len(durations), 1)

        return None

    def get_most_popular_profile(self) -> str | None:
        """Get the most frequently used profile."""
        if not self._profile_usage:
            return None

        # Find profile with highest usage count
        most_used = max(self._profile_usage.items(), key=lambda x: x[1])
        return most_used[0]

    def get_profile_usage_stats(self) -> dict[str, int]:
        """Get profile usage statistics."""
        return self._profile_usage.copy()

    def get_brew_history_count(self) -> int:
        """Get the total number of brew history records."""
        return len(self._brew_history)

    def get_water_usage_count(self) -> int:
        """Get the total number of water usage history records."""
        return len(self._water_usage_history)

    def get_brew_count_for_period(self, days: int) -> int:
        """Get number of brews in the specified period."""
        if not self._brew_history:
            return 0

        cutoff_date = dt_util.now() - timedelta(days=days)

        count = 0
        for record in self._brew_history:
            timestamp_str = record.get("timestamp", "")
            if timestamp_str:
                try:
                    record_dt = datetime.fromisoformat(timestamp_str)
                    if record_dt.tzinfo is None:
                        record_dt = dt_util.as_local(record_dt)
                    if record_dt > cutoff_date:
                        count += 1
                except (ValueError, TypeError):
                    continue

        return count

    def get_last_brew_time(self) -> datetime | None:
        """Get the timestamp of the last brew."""
        if not self._brew_history:
            return None

        # Get the most recent brew
        latest_record = max(self._brew_history, key=lambda x: x.get("timestamp", ""))

        try:
            dt = datetime.fromisoformat(latest_record["timestamp"])
            # Ensure timezone is set
            if dt.tzinfo is None:
                return dt_util.as_local(dt)
            return dt
        except (ValueError, KeyError):
            return None

    def debug_water_usage_history(self) -> None:
        """Debug method to log all water usage history."""
        _LOGGER.info(
            "Water usage history (%d records):", len(self._water_usage_history)
        )
        for i, record in enumerate(self._water_usage_history):
            timestamp = record.get("timestamp", "Unknown")
            water_used = record.get("water_used_ml", 0)
            total_at_time = record.get("total_water_at_time", 0)
            _LOGGER.info(
                "  %d. %s: +%sml (total: %sml)",
                i + 1,
                timestamp,
                water_used,
                total_at_time,
            )

        if not self._water_usage_history:
            _LOGGER.info("  No water usage records found")
            _LOGGER.info(
                "  Current tracking state: last_total_water=%s", self._last_total_water
            )

    async def async_reset_water_tracking(self, current_total_water: int) -> None:
        """Reset water usage tracking with a new baseline."""
        _LOGGER.info(
            "Resetting water usage tracking baseline to %d ml", current_total_water
        )
        self._water_usage_history.clear()
        self._last_total_water = current_total_water
        await self._async_save_history()
        _LOGGER.info("Water usage tracking reset complete")
