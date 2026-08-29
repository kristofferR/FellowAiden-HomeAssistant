from __future__ import annotations

import unittest

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
