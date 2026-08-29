from __future__ import annotations

import unittest

from module_loader import load_fellow_utility_module


class ProfileResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module, cleanup = load_fellow_utility_module("profile_resolution")
        self.addCleanup(cleanup)
        self.profiles = [
            {"id": "guided", "title": "Guided", "lastUsedTime": "1234"},
            {"id": "instant", "title": "Instant", "isDefaultProfile": True},
        ]

    def test_exact_brew_start_match_wins_over_instant_brew_preset(self) -> None:
        result = self.module.resolve_current_profile(
            self.profiles,
            {
                "brewStartTime": "1234",
                "ibSelectedProfileId": "instant",
            },
        )

        self.assertEqual(result.title, "Guided")
        self.assertEqual(result.method, "brew_start_time_match")
        self.assertEqual(result.confidence, "very_high")

    def test_active_profile_wins_during_a_brew(self) -> None:
        result = self.module.resolve_current_profile(
            self.profiles,
            {
                "brewingProfileId": "instant",
                "brewStartTime": "1234",
            },
        )

        self.assertEqual(result.title, "Instant")
        self.assertEqual(result.method, "active_brew")

    def test_instant_brew_preset_remains_a_medium_confidence_fallback(self) -> None:
        result = self.module.resolve_current_profile(
            self.profiles,
            {"ibSelectedProfileId": "instant"},
        )

        self.assertEqual(result.title, "Instant")
        self.assertEqual(result.confidence, "medium")


class TelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module, cleanup = load_fellow_utility_module("telemetry")
        self.addCleanup(cleanup)

    def test_live_state_overrides_stale_brewing_flag(self) -> None:
        self.assertFalse(self.module.is_brewing({"state": None, "brewing": True}))
        self.assertTrue(
            self.module.is_brewing({"state": {"value": "p1"}, "brewing": False})
        )

    def test_brew_phase_codes_are_normalized(self) -> None:
        self.assertEqual(self.module.brew_phase({"state": {"value": "p3"}}), "pulse_3")
        self.assertEqual(self.module.brew_phase({"state": None}), "idle")

    def test_nested_missing_water_is_used(self) -> None:
        self.assertTrue(
            self.module.is_missing_water(
                {
                    "missingWater": False,
                    "state": {"missing_water": True, "value": "pa"},
                }
            )
        )
