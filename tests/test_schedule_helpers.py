from __future__ import annotations

import unittest
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from module_loader import load_fellow_utility_module


class ScheduleHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module, cleanup = load_fellow_utility_module("schedule_helpers")
        self.addCleanup(cleanup)
        self.timezone = ZoneInfo("Europe/Oslo")
        self.profiles = [{"id": "p1", "title": "Morning"}]

    def test_expands_sunday_first_weekday_array(self) -> None:
        schedules = [
            {
                "id": "s1",
                "days": [True, False, False, False, False, False, False],
                "secondFromStartOfTheDay": 7 * 3600 + 30 * 60,
                "enabled": True,
                "amountOfWater": 500,
                "profileId": "p1",
            }
        ]

        events = self.module.schedule_occurrences(
            schedules,
            self.profiles,
            datetime(2026, 8, 29, tzinfo=UTC),
            datetime(2026, 8, 31, tzinfo=UTC),
            self.timezone,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].start.weekday(), 6)
        self.assertEqual(events[0].start.hour, 7)
        self.assertEqual(events[0].start.minute, 30)
        self.assertEqual(events[0].profile_title, "Morning")
        self.assertEqual(events[0].water_ml, 500)

    def test_next_occurrence_skips_disabled_schedules(self) -> None:
        schedules = [
            {
                "days": [True] * 7,
                "secondFromStartOfTheDay": 8 * 3600,
                "enabled": False,
                "amountOfWater": 300,
                "profileId": "p1",
            },
            {
                "days": [True] * 7,
                "secondFromStartOfTheDay": 9 * 3600,
                "enabled": True,
                "amountOfWater": 400,
                "profileId": "p1",
            },
        ]

        occurrence = self.module.next_schedule_occurrence(
            schedules,
            self.profiles,
            datetime(2026, 8, 29, 6, tzinfo=UTC),
            self.timezone,
        )

        self.assertIsNotNone(occurrence)
        self.assertEqual(occurrence.start.hour, 9)
        self.assertEqual(occurrence.water_ml, 400)

    def test_invalid_timezone_falls_back(self) -> None:
        timezone = self.module.schedule_timezone(
            {"deviceTimezone": "not/a-zone"}, "Europe/Oslo"
        )

        self.assertEqual(timezone.key, "Europe/Oslo")
