"""Calendar platform for Fellow Aiden brew schedules."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .base_entity import FellowAidenBaseEntity
from .const import FellowAidenConfigEntry
from .coordinator import FellowAidenDataUpdateCoordinator
from .schedule_helpers import (
    ScheduleOccurrence,
    next_schedule_occurrence,
    schedule_occurrences,
    schedule_timezone,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: FellowAidenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Aiden schedule calendar."""
    async_add_entities([AidenScheduleCalendar(entry.runtime_data, entry)])


class AidenScheduleCalendar(FellowAidenBaseEntity, CalendarEntity):
    """Read-only calendar containing the brewer's recurring schedules."""

    _attr_translation_key = "brew_schedule"

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: FellowAidenConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}-brew-schedule"

    def _timezone(self) -> ZoneInfo:
        data = self.coordinator.data or {}
        return schedule_timezone(
            data.get("device_config", {}),
            self.coordinator.hass.config.time_zone,
        )

    def _event_from_occurrence(self, occurrence: ScheduleOccurrence) -> CalendarEvent:
        summary = occurrence.profile_title or "Scheduled brew"
        if occurrence.water_ml is not None:
            summary = f"{summary} ({occurrence.water_ml} mL)"
        description = f"Repeats: {', '.join(occurrence.repeat_days)}"
        uid = (
            f"{occurrence.schedule_id}:{occurrence.start.date().isoformat()}"
            if occurrence.schedule_id
            else None
        )
        return CalendarEvent(
            start=occurrence.start,
            end=occurrence.start + timedelta(minutes=1),
            summary=summary,
            description=description,
            uid=uid,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next enabled scheduled brew."""
        data = self.coordinator.data or {}
        occurrence = next_schedule_occurrence(
            data.get("schedules") or [],
            data.get("profiles") or [],
            dt_util.now(),
            self._timezone(),
        )
        return self._event_from_occurrence(occurrence) if occurrence else None

    async def async_get_events(
        self,
        _hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return scheduled brews in the requested range."""
        data = self.coordinator.data or {}
        return [
            self._event_from_occurrence(occurrence)
            for occurrence in schedule_occurrences(
                data.get("schedules") or [],
                data.get("profiles") or [],
                start_date,
                end_date,
                self._timezone(),
            )
        ]
