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

    def test_recipe_attributes_exclude_server_metadata(self) -> None:
        attributes = self.module.profile_recipe_attributes(
            {
                "id": "private-id",
                "title": "Personal title",
                "ratio": 16,
                "bloomEnabled": True,
                "bloomTemperature": 96,
                "ssPulseTemperatures": [96, 95],
                "createdAt": "private timestamp",
            }
        )

        self.assertEqual(
            attributes,
            {
                "ratio": 16,
                "bloom_enabled": True,
                "bloom_temperature_c": 96,
                "single_serve_pulse_temperatures_c": [96, 95],
            },
        )


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
        self.assertEqual(
            self.module.brew_phase({"state": {"value": "p10"}}), "pulse_10"
        )
        self.assertEqual(self.module.brew_phase({"state": None}), "idle")
        self.assertEqual(self.module.brew_phase({"brewing": False}), "idle")
        self.assertEqual(self.module.brew_phase({}), "unknown")
        self.assertEqual(self.module.brew_phase({"state": {"value": "p²"}}), "unknown")

    def test_nested_missing_water_is_used(self) -> None:
        self.assertTrue(
            self.module.is_missing_water(
                {
                    "missingWater": False,
                    "state": {"missing_water": True, "value": "pa"},
                }
            )
        )

    def test_brew_error_is_unknown_without_valid_state_data(self) -> None:
        self.assertIsNone(self.module.has_brew_error({}))
        self.assertIsNone(self.module.has_brew_error({"state": "invalid"}))
        self.assertFalse(self.module.has_brew_error({"state": None}))
        self.assertFalse(self.module.has_brew_error({"state": {"value": "p1"}}))
        self.assertTrue(
            self.module.has_brew_error(
                {"state": {"value": "pa", "error": "missing_water"}}
            )
        )

    def test_lifecycle_events_follow_live_state_transitions(self) -> None:
        self.assertEqual(
            self.module.device_events(
                {"state": None, "brewing": True},
                {"state": {"value": "b"}, "brewing": False},
            ),
            ["brew_started"],
        )
        self.assertEqual(
            self.module.device_events(
                {"state": {"value": "p3"}, "missingWater": False},
                {
                    "state": {"value": "pa", "missing_water": True},
                    "missingWater": True,
                },
            ),
            ["brew_paused"],
        )
        self.assertEqual(
            self.module.device_events(
                {"state": {"value": "pa"}, "missingWater": True},
                {"state": {"value": "p4"}, "missingWater": False},
            ),
            ["brew_resumed"],
        )
        self.assertEqual(
            self.module.device_events(
                {"state": {"value": "d"}},
                {"state": None},
            ),
            ["brew_completed"],
        )

    def test_remote_start_requires_safe_reported_state(self) -> None:
        ready = {
            "state": None,
            "isConnected": True,
            "lidClosed": True,
            "missingWater": False,
            "singleBrewBasketPresent": True,
            "cleaning": False,
            "rinsing": False,
        }

        self.assertTrue(self.module.can_start_brew(ready))
        self.assertFalse(self.module.can_start_brew({**ready, "lidClosed": False}))
        self.assertFalse(
            self.module.can_start_brew(
                {key: value for key, value in ready.items() if key != "cleaning"}
            )
        )
        self.assertFalse(
            self.module.can_start_brew(
                {key: value for key, value in ready.items() if key != "rinsing"}
            )
        )
        self.assertFalse(
            self.module.can_start_brew({**ready, "singleBrewBasketPresent": False})
        )
        self.assertTrue(
            self.module.can_start_brew(
                {
                    **ready,
                    "singleBrewBasketPresent": False,
                    "batchBrewBasketPresent": True,
                    "carafePresent": True,
                }
            )
        )
