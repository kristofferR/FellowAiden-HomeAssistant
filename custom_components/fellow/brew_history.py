"""Brew history data management for Fellow Aiden integration."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import storage
from homeassistant.util import dt as dt_util

from .const import HISTORY_RETENTION_DAYS, MIN_HISTORICAL_DATA_FOR_ACCURACY
from .profile_resolution import resolve_current_profile
from .telemetry import is_brewing

_LOGGER = logging.getLogger(__name__)

_TIMING_VERSION = 2
_MAX_LEGACY_DURATION_SECONDS = 30 * 60
_MAX_LEGACY_END_SKEW_SECONDS = 2 * 60
_MAX_COMPLETION_CLOCK_SKEW_SECONDS = 5 * 60
_MAX_OBSERVED_START_AGE_SECONDS = 30 * 60
_TRUSTED_DURATION_SOURCES = frozenset({"observed_cycle", "validated_legacy_pair"})


def _nonnegative_counter(value: Any, *, integral: bool = False) -> int | float | None:
    """Return a valid API counter without treating absence as zero."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        return None
    if integral:
        return int(value) if float(value).is_integer() else None
    return value


def _positive_timestamp(value: Any) -> int | None:
    """Return a positive integral Unix timestamp."""
    if isinstance(value, bool):
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(timestamp) or timestamp <= 0 or not timestamp.is_integer():
        return None
    return int(timestamp)


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
        self._active_brew_start: int | None = None
        self._active_brew_cycles: int | None = None
        self._last_api_brew_start: int | None = None
        self._data_loaded = False

    async def async_load_history(self) -> None:
        """Load historical data from storage."""
        try:
            data = await self._store.async_load()
            timing_migrated = False
            if data is not None:
                self._brew_history = data.get("brew_history", [])
                self._water_usage_history = data.get("water_usage_history", [])
                self._profile_usage = data.get("profile_usage", {})
                self._last_total_brews = data.get("last_total_brews", 0)
                self._last_total_water = data.get("last_total_water", 0)
                # Stored data from older releases already has a valid baseline,
                # even though it predates the explicit initialization flag.
                self._tracking_initialized = data.get("tracking_initialized", True)
                self._active_brew_start = _positive_timestamp(
                    data.get("active_brew_start")
                )
                active_cycles = _nonnegative_counter(
                    data.get("active_brew_cycles"), integral=True
                )
                self._active_brew_cycles = (
                    int(active_cycles) if active_cycles is not None else None
                )
                self._last_api_brew_start = _positive_timestamp(
                    data.get("last_api_brew_start")
                )
                if data.get("timing_version") != _TIMING_VERSION:
                    self._migrate_legacy_timing()
                    timing_migrated = True
                _LOGGER.debug(
                    "Loaded brew history: %d brews, %d water records",
                    len(self._brew_history),
                    len(self._water_usage_history),
                )
            self._data_loaded = True
            if timing_migrated:
                await self._async_save_history()
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
                "active_brew_start": self._active_brew_start,
                "active_brew_cycles": self._active_brew_cycles,
                "last_api_brew_start": self._last_api_brew_start,
                "timing_version": _TIMING_VERSION,
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

        current_total_brews = _nonnegative_counter(
            device_config.get("totalBrewingCycles"), integral=True
        )
        current_total_water = _nonnegative_counter(
            device_config.get("totalWaterVolumeL")
        )
        if current_total_brews is None or current_total_water is None:
            _LOGGER.debug("Skipping history update because counters are unavailable")
            return
        now = dt_util.now()
        data_changed = False
        observed_timing: tuple[int, int, int] | None = None
        current_api_start = _positive_timestamp(device_config.get("brewStartTime"))
        brewing = is_brewing(device_config)

        if brewing is True and self._active_brew_start is None:
            now_timestamp = int(now.timestamp())
            api_start_changed = (
                current_api_start is not None
                and current_api_start != self._last_api_brew_start
                and current_api_start >= now_timestamp - _MAX_OBSERVED_START_AGE_SECONDS
                and current_api_start <= now_timestamp + 60
            )
            self._active_brew_start = (
                current_api_start if api_start_changed else now_timestamp
            )
            self._active_brew_cycles = current_total_brews
            data_changed = True
        elif brewing is False and self._active_brew_start is not None:
            active_cycles = self._active_brew_cycles
            if active_cycles is not None and current_total_brews > active_cycles:
                now_timestamp = int(now.timestamp())
                api_end = _positive_timestamp(device_config.get("brewEndTime"))
                end_timestamp = (
                    api_end
                    if api_end is not None
                    and api_end >= self._active_brew_start
                    and abs(now_timestamp - api_end)
                    <= _MAX_COMPLETION_CLOCK_SKEW_SECONDS
                    else now_timestamp
                )
                duration = end_timestamp - self._active_brew_start
                if duration > 0:
                    observed_timing = (
                        self._active_brew_start,
                        end_timestamp,
                        duration,
                    )
            self._active_brew_start = None
            self._active_brew_cycles = None
            data_changed = True

        if current_api_start != self._last_api_brew_start:
            self._last_api_brew_start = current_api_start
            data_changed = True

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

                if observed_timing is not None and i == new_brews - 1:
                    start_timestamp, end_timestamp, duration = observed_timing
                    brew_record.update(
                        {
                            "start_time": dt_util.as_local(
                                dt_util.utc_from_timestamp(start_timestamp)
                            ).isoformat(),
                            "end_time": dt_util.as_local(
                                dt_util.utc_from_timestamp(end_timestamp)
                            ).isoformat(),
                            "duration_seconds": duration,
                            "duration_source": "observed_cycle",
                        }
                    )

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

    def _migrate_legacy_timing(self) -> None:
        """Keep only a plausible latest legacy pair; discard other derived timing."""
        if not self._brew_history:
            return

        latest = self._brew_history[-1]
        candidate = {
            key: latest.get(key)
            for key in ("start_time", "end_time", "duration_seconds")
        }
        for record in self._brew_history:
            for key in (
                "start_time",
                "end_time",
                "duration_seconds",
                "duration_source",
            ):
                record.pop(key, None)

        duration = _nonnegative_counter(candidate["duration_seconds"], integral=True)
        if (
            duration is None
            or duration == 0
            or duration > _MAX_LEGACY_DURATION_SECONDS
            or latest.get("total_brews_at_time") != self._last_total_brews
        ):
            return

        try:
            start = datetime.fromisoformat(str(candidate["start_time"]))
            end = datetime.fromisoformat(str(candidate["end_time"]))
            recorded = datetime.fromisoformat(str(latest["timestamp"]))
            paired_duration = round((end - start).total_seconds())
            end_skew = abs((recorded - end).total_seconds())
        except (KeyError, TypeError, ValueError):
            return

        if paired_duration != duration or end_skew > _MAX_LEGACY_END_SKEW_SECONDS:
            return
        latest.update(
            {
                **candidate,
                "duration_seconds": int(duration),
                "duration_source": "validated_legacy_pair",
            }
        )

    async def async_has_new_brew(self, device_config: dict[str, Any]) -> bool:
        """Return whether fresh profiles are needed for brew attribution."""
        if not self._data_loaded:
            await self.async_load_history()
        current_total_brews = _nonnegative_counter(
            device_config.get("totalBrewingCycles"), integral=True
        )
        return bool(
            self._tracking_initialized
            and current_total_brews is not None
            and current_total_brews > self._last_total_brews
        )

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

    def get_most_popular_profile(self) -> str | None:
        """Get the most frequently used profile."""
        if not self._profile_usage:
            return None

        # Find profile with highest usage count
        most_used = max(self._profile_usage.items(), key=lambda x: x[1])
        return most_used[0]

    def get_last_brew_duration(self) -> int | None:
        """Return the newest duration captured from one observed brew cycle."""
        for record in reversed(self._brew_history):
            if record.get("duration_source") not in _TRUSTED_DURATION_SOURCES:
                continue
            duration = _nonnegative_counter(
                record.get("duration_seconds"), integral=True
            )
            if duration is not None and duration > 0:
                return int(duration)
        return None

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
