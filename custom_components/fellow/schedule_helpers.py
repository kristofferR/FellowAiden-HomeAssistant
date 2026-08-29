"""Turn Fellow's recurring schedules into Home Assistant occurrences."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAY_NAMES = (
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
)


@dataclass(frozen=True, slots=True)
class ScheduleOccurrence:
    """One concrete occurrence of a recurring Fellow schedule."""

    start: datetime
    schedule_id: str | None
    profile_title: str | None
    water_ml: int | None
    repeat_days: tuple[str, ...]


def schedule_timezone(device_config: dict[str, Any], fallback: str) -> ZoneInfo:
    """Return the brewer timezone, then HA's timezone, then UTC."""
    for candidate in (device_config.get("deviceTimezone"), fallback, "UTC"):
        if not isinstance(candidate, str) or not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            continue
    return ZoneInfo("UTC")


def schedule_occurrences(
    schedules: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    timezone: tzinfo,
) -> list[ScheduleOccurrence]:
    """Expand enabled weekly schedules within a half-open time range."""
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        return []

    profile_titles = {
        profile.get("id"): profile.get("title")
        for profile in profiles
        if isinstance(profile.get("id"), str) and isinstance(profile.get("title"), str)
    }
    local_start = start.astimezone(timezone)
    local_end = end.astimezone(timezone)
    first_date = local_start.date()
    days_to_check = (local_end.date() - first_date).days + 1
    occurrences: list[ScheduleOccurrence] = []

    for schedule in schedules:
        days = schedule.get("days")
        seconds = schedule.get("secondFromStartOfTheDay")
        if (
            schedule.get("enabled") is not True
            or not isinstance(days, list)
            or len(days) != 7
            or isinstance(seconds, bool)
            or not isinstance(seconds, int)
            or not 0 <= seconds < 86_400
        ):
            continue

        repeat_days = tuple(
            WEEKDAY_NAMES[index]
            for index, enabled in enumerate(days)
            if enabled is True
        )
        if not repeat_days:
            continue

        water = schedule.get("amountOfWater")
        water_ml = (
            water
            if isinstance(water, int) and not isinstance(water, bool) and water > 0
            else None
        )
        schedule_id = schedule.get("id")
        if not isinstance(schedule_id, str):
            schedule_id = None
        profile_title = profile_titles.get(schedule.get("profileId"))

        for offset in range(days_to_check):
            date = first_date + timedelta(days=offset)
            api_weekday = (date.weekday() + 1) % 7
            if days[api_weekday] is not True:
                continue
            occurrence_start = datetime.combine(
                date,
                datetime.min.time(),
                tzinfo=timezone,
            ) + timedelta(seconds=seconds)
            if start <= occurrence_start < end:
                occurrences.append(
                    ScheduleOccurrence(
                        start=occurrence_start,
                        schedule_id=schedule_id,
                        profile_title=profile_title,
                        water_ml=water_ml,
                        repeat_days=repeat_days,
                    )
                )

    return sorted(occurrences, key=lambda occurrence: occurrence.start)


def next_schedule_occurrence(
    schedules: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    now: datetime,
    timezone: tzinfo,
) -> ScheduleOccurrence | None:
    """Return the next enabled occurrence within the weekly cycle."""
    occurrences = schedule_occurrences(
        schedules,
        profiles,
        now,
        now + timedelta(days=8),
        timezone,
    )
    return occurrences[0] if occurrences else None
