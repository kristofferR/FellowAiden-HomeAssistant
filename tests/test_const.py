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
