from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

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
        self.fast_poll_activations = 0

    def set_push_manager(self, manager: object) -> None:
        self.push_manager = manager

    def set_push_connected(self, connected: bool) -> None:
        self.connected_states.append(connected)

    def async_update_listeners(self) -> None:
        self.listener_updates += 1

    def activate_fast_polling(self) -> None:
        self.fast_poll_activations += 1

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
        self.assertEqual(coordinator.fast_poll_activations, 2)
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

    async def test_successful_connection_resets_reconnect_backoff(self) -> None:
        manager = self.module.FellowPushManager(FakeHass(), "account")
        manager._retry_delay = 80

        await manager._async_connection_changed(True)

        self.assertEqual(manager._retry_delay, self.module._INITIAL_RETRY_SECONDS)
        self.assertEqual(manager.status, self.module.PushStatus.CONNECTED)

    async def test_registration_rejection_discards_stored_credentials(self) -> None:
        module = self.module

        class FakeApi:
            def __init__(self) -> None:
                self.tokens: list[str] = []

            async def register_push_token(self, token: str) -> None:
                self.tokens.append(token)

        class FakeClient:
            def __init__(self) -> None:
                self.existing_credentials: list[object] = []

            async def async_register(self, existing: object) -> object:
                self.existing_credentials.append(existing)
                if len(self.existing_credentials) == 1:
                    raise module.FcmRegistrationRejectedError("rejected")
                return module.FcmCredentials(3, 4, "fresh-token")

        manager = module.FellowPushManager(FakeHass(), "account")
        coordinator = FakeCoordinator()
        coordinator.api = FakeApi()
        manager.attach("entry-1", coordinator)
        stale_credentials = module.FcmCredentials(1, 2, "stale-token")
        manager._credentials = stale_credentials
        client = FakeClient()
        saved: list[dict[str, object]] = []

        async def save(data: dict[str, object]) -> None:
            saved.append(data)

        with (
            patch.object(manager._store, "async_save", side_effect=save),
            patch.object(manager, "_async_retry_delay", return_value=None) as retry,
        ):
            registered = await manager._async_register(client)

        self.assertTrue(registered)
        self.assertEqual(client.existing_credentials, [stale_credentials, None])
        self.assertEqual(saved[0], {})
        self.assertEqual(saved[-1]["fcm_token"], "fresh-token")
        self.assertEqual(coordinator.api.tokens, ["fresh-token"])
        retry.assert_awaited_once_with()

    async def test_transient_registration_failure_preserves_credentials(self) -> None:
        module = self.module

        class FakeApi:
            async def register_push_token(self, _token: str) -> None:
                return None

        class FakeClient:
            def __init__(self) -> None:
                self.existing_credentials: list[object] = []

            async def async_register(self, existing: object) -> object:
                self.existing_credentials.append(existing)
                if len(self.existing_credentials) == 1:
                    raise module.FcmError("network failure")
                return existing

        manager = module.FellowPushManager(FakeHass(), "account")
        coordinator = FakeCoordinator()
        coordinator.api = FakeApi()
        manager.attach("entry-1", coordinator)
        credentials = module.FcmCredentials(1, 2, "token", ["persistent-id"])
        manager._credentials = credentials
        client = FakeClient()

        with patch.object(manager, "_async_retry_delay", return_value=None) as retry:
            registered = await manager._async_register(client)

        self.assertTrue(registered)
        self.assertEqual(client.existing_credentials, [credentials, credentials])
        self.assertEqual(manager._store.data["persistent_ids"], ["persistent-id"])
        retry.assert_awaited_once_with()

    async def test_rejected_credentials_trigger_fresh_registration(self) -> None:
        module = self.module

        class FakeApi:
            def __init__(self) -> None:
                self.tokens: list[str] = []

            async def register_push_token(self, token: str) -> None:
                self.tokens.append(token)

        class FakeClient:
            def __init__(self, manager: object) -> None:
                self.manager = manager
                self.existing_credentials = []
                self.listen_count = 0

            async def async_register(self, existing: object) -> object:
                self.existing_credentials.append(existing)
                suffix = len(self.existing_credentials)
                return module.FcmCredentials(suffix, suffix, f"token-{suffix}")

            async def async_listen(self, *_args: object) -> None:
                self.listen_count += 1
                if self.listen_count == 1:
                    raise module.FcmAuthenticationError("rejected")
                self.manager.detach("entry-1")

        hass = FakeHass()
        manager = self.module.FellowPushManager(hass, "account")
        coordinator = FakeCoordinator()
        coordinator.api = FakeApi()
        manager.attach("entry-1", coordinator)
        client = FakeClient(manager)

        with (
            patch.object(self.module, "FcmClient", return_value=client),
            patch.object(manager, "_async_retry_delay", return_value=None) as retry,
        ):
            await manager._async_run()

        self.assertEqual(client.existing_credentials, [None, None])
        self.assertEqual(client.listen_count, 2)
        retry.assert_awaited_once_with()
