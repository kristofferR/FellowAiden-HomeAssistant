from __future__ import annotations

import unittest

from module_loader import load_fellow_utility_module


class UpdateIntervalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module, cleanup = load_fellow_utility_module("const")
        self.addCleanup(cleanup)

    def test_seconds_option_takes_precedence(self) -> None:
        self.assertEqual(
            self.module.get_update_interval_seconds(
                {"update_interval_seconds": 20, "update_interval_minutes": 2}
            ),
            20,
        )

    def test_legacy_minutes_are_preserved(self) -> None:
        self.assertEqual(
            self.module.get_update_interval_seconds({"update_interval_minutes": 2}),
            120,
        )

    def test_default_is_used_without_an_option(self) -> None:
        self.assertEqual(
            self.module.get_update_interval_seconds({}),
            self.module.DEFAULT_UPDATE_INTERVAL_SECONDS,
        )

    def test_adaptive_interval_uses_fast_polling_during_activity(self) -> None:
        self.assertEqual(
            self.module.get_adaptive_update_interval_seconds(
                30,
                push_connected=True,
                recently_active=True,
            ),
            10,
        )

    def test_adaptive_interval_uses_fast_polling_without_push(self) -> None:
        self.assertEqual(
            self.module.get_adaptive_update_interval_seconds(
                30,
                push_connected=False,
                recently_active=True,
            ),
            10,
        )

    def test_adaptive_interval_slows_idle_polling_when_push_is_connected(
        self,
    ) -> None:
        self.assertEqual(
            self.module.get_adaptive_update_interval_seconds(
                30,
                push_connected=True,
                recently_active=False,
            ),
            60,
        )

    def test_adaptive_interval_uses_configured_fallback_without_push(self) -> None:
        self.assertEqual(
            self.module.get_adaptive_update_interval_seconds(
                45,
                push_connected=False,
                recently_active=False,
            ),
            45,
        )
