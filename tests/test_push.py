from __future__ import annotations

import asyncio
import unittest

from module_loader import load_push_module


class FakeBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def async_fire(self, event_type: str, data: dict[str, object]) -> None:
        self.events.append((event_type, data))


class FakeHass:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}
        self.bus = FakeBus()
        self.session = object()

    def async_create_background_task(
        self, coroutine: object, name: str
    ) -> asyncio.Task:
        del name
        return asyncio.create_task(coroutine)


class FakeCoordinator:
    def __init__(self) -> None:
        self.api = None
        self.push_manager = None
        self.connected_states: list[bool] = []
        self.listener_updates = 0
        self.refreshes = 0

    def set_push_manager(self, manager: object) -> None:
        self.push_manager = manager

    def set_push_connected(self, connected: bool) -> None:
        self.connected_states.append(connected)

    def async_update_listeners(self) -> None:
        self.listener_updates += 1

    async def async_request_refresh(self) -> None:
        self.refreshes += 1


class PushManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.module, cleanup = load_push_module()
        self.addCleanup(cleanup)

    async def test_message_fires_event_persists_id_and_debounces_refresh(self) -> None:
        hass = FakeHass()
        manager = self.module.FellowPushManager(hass, "account")
        coordinator = FakeCoordinator()
        manager.attach("entry-1", coordinator)
        manager._credentials = self.module.FcmCredentials(1, 2, "private-token")
        manager._credentials.persistent_ids.append("persistent-1")
        message = self.module.FcmMessage(
            category="com.fellowproducts.Fellow",
            data={"type": "brew-complete"},
            persistent_id="persistent-1",
        )

        original_delay = self.module._REFRESH_DEBOUNCE_SECONDS
        self.module._REFRESH_DEBOUNCE_SECONDS = 0
        try:
            await manager._async_message(message)
            await manager._async_message(message)
            await manager._refresh_task
        finally:
            self.module._REFRESH_DEBOUNCE_SECONDS = original_delay

        self.assertEqual(manager.message_count, 2)
        self.assertEqual(coordinator.refreshes, 1)
        self.assertEqual(hass.bus.events[0][0], self.module.EVENT_CLOUD_PUSH)
        self.assertEqual(
            hass.bus.events[0][1],
            {
                "config_entry_ids": ["entry-1"],
                "category": "com.fellowproducts.Fellow",
                "data": {"type": "brew-complete"},
            },
        )
        self.assertNotIn("private-token", str(hass.bus.events))
        self.assertEqual(manager._store.data["persistent_ids"], ["persistent-1"])
        self.assertGreaterEqual(coordinator.listener_updates, 2)
