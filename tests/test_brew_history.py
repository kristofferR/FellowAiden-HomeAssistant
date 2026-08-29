from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from module_loader import load_brew_history_module


class BrewHistoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.module, cleanup = load_brew_history_module()
        self.addCleanup(cleanup)
        self.manager = self.module.BrewHistoryManager(object(), "entry")

    async def test_first_brew_after_zero_baseline_is_recorded(self) -> None:
        profiles = [
            {"id": "guided", "title": "Guided", "lastUsedTime": "1234"},
            {"id": "instant", "title": "Instant"},
        ]
        await self.manager.async_update_data(
            {"totalBrewingCycles": 0, "totalWaterVolumeL": 0}, profiles
        )

        await self.manager.async_update_data(
            {
                "totalBrewingCycles": 1,
                "totalWaterVolumeL": 500,
                "brewStartTime": "1234",
                "ibSelectedProfileId": "instant",
            },
            profiles,
        )
        await self.manager.async_update_data(
            {
                "totalBrewingCycles": 2,
                "totalWaterVolumeL": 750,
                "brewStartTime": "1234",
                "ibSelectedProfileId": "instant",
            },
            profiles,
        )

        self.assertEqual(self.manager.get_brew_history_count(), 2)
        self.assertEqual(self.manager.get_water_usage_count(), 2)
        self.assertEqual(self.manager.get_water_usage_for_period(1), 0.75)
        self.assertEqual(self.manager.get_profile_usage_stats(), {"Guided": 2})

    async def test_partial_counters_do_not_reset_history_baseline(self) -> None:
        await self.manager.async_update_data(
            {"totalBrewingCycles": 10, "totalWaterVolumeL": 5000}, []
        )

        await self.manager.async_update_data({"totalBrewingCycles": 10}, [])
        await self.manager.async_update_data({"totalWaterVolumeL": 5000}, [])
        await self.manager.async_update_data(
            {"totalBrewingCycles": 10, "totalWaterVolumeL": 5000}, []
        )

        self.assertEqual(self.manager.get_brew_history_count(), 0)
        self.assertEqual(self.manager.get_water_usage_count(), 0)
        self.assertEqual(self.manager._last_total_brews, 10)
        self.assertEqual(self.manager._last_total_water, 5000)

    async def test_partial_counters_still_preserve_observed_cycle_timing(self) -> None:
        started = datetime.fromtimestamp(1788012278, UTC)
        finished = datetime.fromtimestamp(1788012398, UTC)
        counter_updated = datetime.fromtimestamp(1788012408, UTC)
        with patch.object(self.module.dt_util, "now", return_value=started):
            await self.manager.async_update_data(
                {
                    "totalBrewingCycles": 10,
                    "totalWaterVolumeL": 5000,
                    "state": None,
                },
                [],
            )
            await self.manager.async_update_data(
                {
                    "state": {"value": "p1"},
                    "brewStartTime": str(int(started.timestamp())),
                },
                [],
            )
        with patch.object(self.module.dt_util, "now", return_value=finished):
            await self.manager.async_update_data(
                {
                    "state": None,
                    "brewStartTime": str(int(started.timestamp())),
                    "brewEndTime": str(int(finished.timestamp())),
                },
                [],
            )
        with patch.object(self.module.dt_util, "now", return_value=counter_updated):
            await self.manager.async_update_data(
                {
                    "totalBrewingCycles": 11,
                    "totalWaterVolumeL": 5450,
                    "state": None,
                },
                [],
            )

        self.assertEqual(self.manager.get_last_brew_duration(), 120)

    async def test_detects_when_fresh_profiles_are_needed(self) -> None:
        await self.manager.async_update_data(
            {"totalBrewingCycles": 10, "totalWaterVolumeL": 5000}, []
        )

        self.assertFalse(
            await self.manager.async_has_new_brew(
                {"totalBrewingCycles": 10, "totalWaterVolumeL": 5000}
            )
        )
        self.assertTrue(
            await self.manager.async_has_new_brew(
                {"totalBrewingCycles": 11, "totalWaterVolumeL": 5500}
            )
        )
        self.assertFalse(await self.manager.async_has_new_brew({}))

    async def test_unpaired_api_timestamps_are_not_stored_as_duration(self) -> None:
        await self.manager.async_update_data(
            {"totalBrewingCycles": 10, "totalWaterVolumeL": 5000}, []
        )

        await self.manager.async_update_data(
            {
                "totalBrewingCycles": 11,
                "totalWaterVolumeL": 5500,
                "brewStartTime": "1788001438",
                "brewEndTime": "1788008322",
            },
            [],
        )

        record = self.manager._brew_history[-1]
        self.assertNotIn("start_time", record)
        self.assertNotIn("end_time", record)
        self.assertNotIn("duration_seconds", record)

    async def test_observed_cycle_stores_paired_duration(self) -> None:
        now = datetime.fromtimestamp(1788012278, UTC)
        with patch.object(self.module.dt_util, "now", return_value=now):
            await self.manager.async_update_data(
                {
                    "totalBrewingCycles": 10,
                    "totalWaterVolumeL": 5000,
                    "brewing": False,
                    "brewStartTime": "1788001438",
                },
                [],
            )
            await self.manager.async_update_data(
                {
                    "totalBrewingCycles": 10,
                    "totalWaterVolumeL": 5000,
                    "brewing": True,
                    "brewStartTime": "1788011867",
                },
                [],
            )
            await self.manager.async_update_data(
                {
                    "totalBrewingCycles": 11,
                    "totalWaterVolumeL": 5450,
                    "brewing": False,
                    "brewStartTime": "1788011867",
                    "brewEndTime": "1788012276",
                },
                [],
            )

        record = self.manager._brew_history[-1]
        self.assertEqual(record["duration_seconds"], 409)
        self.assertEqual(record["duration_source"], "observed_cycle")
        self.assertEqual(self.manager.get_last_brew_duration(), 409)

    async def test_live_state_drives_observed_cycle_when_flag_is_stale(self) -> None:
        started = datetime.fromtimestamp(1788012278, UTC)
        finished = datetime.fromtimestamp(1788012398, UTC)
        with patch.object(self.module.dt_util, "now", return_value=started):
            await self.manager.async_update_data(
                {
                    "totalBrewingCycles": 10,
                    "totalWaterVolumeL": 5000,
                    "state": None,
                    "brewing": True,
                },
                [],
            )
            await self.manager.async_update_data(
                {
                    "totalBrewingCycles": 10,
                    "totalWaterVolumeL": 5000,
                    "state": {"value": "p1"},
                    "brewing": False,
                },
                [],
            )
        with patch.object(self.module.dt_util, "now", return_value=finished):
            await self.manager.async_update_data(
                {
                    "totalBrewingCycles": 11,
                    "totalWaterVolumeL": 5450,
                    "state": None,
                    "brewing": True,
                    "brewEndTime": "1788012398",
                },
                [],
            )

        self.assertEqual(self.manager.get_last_brew_duration(), 120)

    async def test_timing_is_attached_when_counter_advances_during_brew(self) -> None:
        started = datetime.fromtimestamp(1788012278, UTC)
        midway = datetime.fromtimestamp(1788012338, UTC)
        finished = datetime.fromtimestamp(1788012398, UTC)
        baseline = {
            "totalBrewingCycles": 10,
            "totalWaterVolumeL": 5000,
            "state": None,
        }
        with patch.object(self.module.dt_util, "now", return_value=started):
            await self.manager.async_update_data(baseline, [])
            await self.manager.async_update_data(
                {
                    **baseline,
                    "state": {"value": "p1"},
                    "brewStartTime": str(int(started.timestamp())),
                },
                [],
            )
        with patch.object(self.module.dt_util, "now", return_value=midway):
            await self.manager.async_update_data(
                {
                    **baseline,
                    "totalBrewingCycles": 11,
                    "totalWaterVolumeL": 5450,
                    "state": {"value": "p2"},
                    "brewStartTime": str(int(started.timestamp())),
                },
                [],
            )
        self.assertNotIn("duration_seconds", self.manager._brew_history[-1])

        with patch.object(self.module.dt_util, "now", return_value=finished):
            await self.manager.async_update_data(
                {
                    **baseline,
                    "totalBrewingCycles": 11,
                    "totalWaterVolumeL": 5450,
                    "brewStartTime": str(int(started.timestamp())),
                    "brewEndTime": str(int(finished.timestamp())),
                },
                [],
            )

        self.assertEqual(self.manager.get_last_brew_duration(), 120)
        self.assertEqual(
            self.manager._brew_history[-1]["duration_source"], "observed_cycle"
        )

    async def test_timing_waits_for_counter_after_brew_finishes(self) -> None:
        started = datetime.fromtimestamp(1788012278, UTC)
        finished = datetime.fromtimestamp(1788012398, UTC)
        counter_updated = datetime.fromtimestamp(1788012408, UTC)
        baseline = {
            "totalBrewingCycles": 10,
            "totalWaterVolumeL": 5000,
            "state": None,
        }
        with patch.object(self.module.dt_util, "now", return_value=started):
            await self.manager.async_update_data(baseline, [])
            await self.manager.async_update_data(
                {
                    **baseline,
                    "state": {"value": "p1"},
                    "brewStartTime": str(int(started.timestamp())),
                },
                [],
            )
        with patch.object(self.module.dt_util, "now", return_value=finished):
            await self.manager.async_update_data(
                {
                    **baseline,
                    "brewStartTime": str(int(started.timestamp())),
                    "brewEndTime": str(int(finished.timestamp())),
                },
                [],
            )

        self.assertEqual(self.manager.get_brew_history_count(), 0)
        self.assertIsNotNone(self.manager._pending_brew_timing)

        with patch.object(self.module.dt_util, "now", return_value=counter_updated):
            await self.manager.async_update_data(
                {
                    **baseline,
                    "totalBrewingCycles": 11,
                    "totalWaterVolumeL": 5450,
                    "brewStartTime": str(int(started.timestamp())),
                    "brewEndTime": str(int(finished.timestamp())),
                },
                [],
            )

        self.assertIsNone(self.manager._pending_brew_timing)
        self.assertEqual(self.manager.get_last_brew_duration(), 120)

    async def test_pending_timing_expires_before_an_unrelated_counter_change(
        self,
    ) -> None:
        started = datetime.fromtimestamp(1788012278, UTC)
        finished = datetime.fromtimestamp(1788012398, UTC)
        expired = datetime.fromtimestamp(
            int(finished.timestamp())
            + self.module._MAX_PENDING_COMPLETION_AGE_SECONDS
            + 1,
            UTC,
        )
        baseline = {
            "totalBrewingCycles": 10,
            "totalWaterVolumeL": 5000,
            "state": None,
        }
        with patch.object(self.module.dt_util, "now", return_value=started):
            await self.manager.async_update_data(baseline, [])
            await self.manager.async_update_data(
                {**baseline, "state": {"value": "p1"}}, []
            )
        with patch.object(self.module.dt_util, "now", return_value=finished):
            await self.manager.async_update_data(baseline, [])
        with patch.object(self.module.dt_util, "now", return_value=expired):
            await self.manager.async_update_data(baseline, [])
            await self.manager.async_update_data(
                {
                    **baseline,
                    "totalBrewingCycles": 11,
                    "totalWaterVolumeL": 5450,
                },
                [],
            )

        self.assertIsNone(self.manager._pending_brew_timing)
        self.assertIsNone(self.manager.get_last_brew_duration())

    async def test_failed_profile_refresh_does_not_defer_cycle_timing(self) -> None:
        started = datetime.fromtimestamp(1788012278, UTC)
        finished = datetime.fromtimestamp(1788012398, UTC)
        device = {
            "totalBrewingCycles": 10,
            "totalWaterVolumeL": 5000,
            "state": None,
        }
        with patch.object(self.module.dt_util, "now", return_value=started):
            await self.manager.async_update_data(device, [])
            await self.manager.async_update_data(
                {
                    **device,
                    "state": {"value": "p1"},
                    "brewStartTime": str(int(started.timestamp())),
                },
                [],
            )
        completed_device = {
            **device,
            "totalBrewingCycles": 11,
            "totalWaterVolumeL": 5450,
            "brewStartTime": str(int(started.timestamp())),
            "brewEndTime": str(int(finished.timestamp())),
        }
        with patch.object(self.module.dt_util, "now", return_value=finished):
            await self.manager.async_update_data(completed_device, [])

        record = self.manager._brew_history[-1]
        self.assertEqual(record["duration_seconds"], 120)
        self.assertNotIn("profile_title", record)
        self.assertTrue(
            await self.manager.async_needs_profile_attribution(completed_device)
        )

        profiles = [
            {
                "id": "guided",
                "title": "Guided",
                "lastUsedTime": str(int(started.timestamp())),
            }
        ]
        await self.manager.async_update_data(completed_device, profiles)
        await self.manager.async_update_data(completed_device, profiles)

        self.assertEqual(record["duration_seconds"], 120)
        self.assertEqual(record["profile_id"], "guided")
        self.assertEqual(record["profile_title"], "Guided")
        self.assertEqual(self.manager.get_profile_usage_stats(), {"Guided": 1})
        self.assertFalse(
            await self.manager.async_needs_profile_attribution(completed_device)
        )

    async def test_profile_backfill_uses_completed_brew_evidence(self) -> None:
        await self.manager.async_update_data(
            {"totalBrewingCycles": 10, "totalWaterVolumeL": 5000}, []
        )
        await self.manager.async_update_data(
            {
                "totalBrewingCycles": 11,
                "totalWaterVolumeL": 5450,
                "brewingProfileId": "completed-profile",
                "brewStartTime": "1234",
            },
            [],
        )

        await self.manager.async_update_data(
            {
                "totalBrewingCycles": 11,
                "totalWaterVolumeL": 5450,
                "state": {"value": "p1"},
                "brewingProfileId": "next-profile",
                "brewStartTime": "5678",
            },
            [
                {"id": "completed-profile", "title": "Completed"},
                {"id": "next-profile", "title": "Next"},
            ],
        )

        record = self.manager._brew_history[-1]
        self.assertEqual(record["profile_id"], "completed-profile")
        self.assertEqual(record["profile_title"], "Completed")
        self.assertNotIn("_profile_evidence", record)

    async def test_stale_active_start_falls_back_to_observation_time(self) -> None:
        initial = datetime.fromtimestamp(1788012278, UTC)
        finished = datetime.fromtimestamp(1788012398, UTC)
        await self.manager.async_update_data(
            {
                "totalBrewingCycles": 10,
                "totalWaterVolumeL": 5000,
                "state": None,
            },
            [],
        )
        with patch.object(self.module.dt_util, "now", return_value=initial):
            await self.manager.async_update_data(
                {
                    "totalBrewingCycles": 10,
                    "totalWaterVolumeL": 5000,
                    "state": {"value": "p1"},
                    "brewStartTime": "1000",
                },
                [],
            )
        with patch.object(self.module.dt_util, "now", return_value=finished):
            await self.manager.async_update_data(
                {
                    "totalBrewingCycles": 11,
                    "totalWaterVolumeL": 5450,
                    "state": None,
                    "brewEndTime": str(int(finished.timestamp())),
                },
                [],
            )

        self.assertEqual(self.manager.get_last_brew_duration(), 120)

    async def test_migration_keeps_only_plausible_latest_duration(self) -> None:
        self.manager._store.data = {
            "brew_history": [
                {
                    "timestamp": "2026-08-29T14:04:59+00:00",
                    "total_brews_at_time": 225,
                    "start_time": "2026-08-29T13:57:47+00:00",
                    "end_time": "2026-08-29T14:04:36+00:00",
                    "duration_seconds": 409,
                }
            ],
            "water_usage_history": [],
            "profile_usage": {},
            "last_total_brews": 225,
            "last_total_water": 105017,
            "tracking_initialized": True,
        }

        await self.manager.async_load_history()

        self.assertEqual(self.manager.get_last_brew_duration(), 409)
        self.assertEqual(self.manager._store.data["timing_version"], 2)

    async def test_migration_discards_mismatched_idle_timestamps(self) -> None:
        self.manager._store.data = {
            "brew_history": [
                {
                    "timestamp": "2026-08-29T12:58:59+00:00",
                    "total_brews_at_time": 224,
                    "start_time": "2026-08-29T11:03:58+00:00",
                    "end_time": "2026-08-29T12:58:42+00:00",
                    "duration_seconds": 6884,
                }
            ],
            "water_usage_history": [],
            "profile_usage": {},
            "last_total_brews": 224,
            "last_total_water": 104567,
            "tracking_initialized": True,
        }

        await self.manager.async_load_history()

        self.assertIsNone(self.manager.get_last_brew_duration())
        self.assertNotIn("duration_seconds", self.manager._brew_history[-1])
