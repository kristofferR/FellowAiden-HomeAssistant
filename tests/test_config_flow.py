from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from module_loader import load_config_flow_module


class ConfigFlowErrorMappingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.module, cleanup = load_config_flow_module()
        self.addCleanup(cleanup)

    async def test_async_step_user_maps_known_login_errors(self) -> None:
        cases = [
            (self.module.FellowAuthError("bad creds"), "auth"),
            (self.module.FellowConnectionError("offline"), "cannot_connect"),
            (
                self.module.FellowNoSupportedDeviceError("no brewer"),
                "unsupported_device",
            ),
            (RuntimeError("unexpected"), "unknown"),
        ]

        for error, expected in cases:
            async def failing_login(
                hass: object, email: str, password: str, *, exc: Exception = error
            ) -> None:
                del hass, email, password
                raise exc

            with self.subTest(expected=expected), patch.object(
                self.module, "_try_login", new=failing_login
            ):
                flow = self.module.FellowAidenConfigFlow()
                flow.hass = types.SimpleNamespace(session=object())

                result = await flow.async_step_user(
                    {"email": "user@example.com", "password": "secret"}
                )

                self.assertEqual(result["type"], "form")
                self.assertEqual(result["errors"]["base"], expected)

    async def test_multi_device_account_prompts_for_brewer(self) -> None:
        devices = [
            {"id": "aiden-1", "displayName": "His"},
            {"id": "aiden-2", "displayName": "Hers"},
        ]

        async def successful_login(
            hass: object, email: str, password: str
        ) -> list[dict[str, str]]:
            del hass, email, password
            return devices

        with patch.object(self.module, "_try_login", new=successful_login):
            flow = self.module.FellowAidenConfigFlow()
            flow.hass = types.SimpleNamespace(session=object())

            result = await flow.async_step_user(
                {"email": "user@example.com", "password": "secret"}
            )
            self.assertEqual(result["type"], "form")
            self.assertEqual(result["step_id"], "device")

            result = await flow.async_step_device(
                {"brewer_id": "aiden-2"}
            )

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "Hers")
        self.assertEqual(
            result["data"],
            {
                "email": "user@example.com",
                "password": "secret",
                "brewer_id": "aiden-2",
            },
        )
        self.assertEqual(flow._unique_id, "aiden-2")

    async def test_already_configured_brewer_is_filtered_out(self) -> None:
        devices = [
            {"id": "aiden-1", "displayName": "His"},
            {"id": "aiden-2", "displayName": "Hers"},
        ]

        async def successful_login(
            hass: object, email: str, password: str
        ) -> list[dict[str, str]]:
            del hass, email, password
            return devices

        with patch.object(self.module, "_try_login", new=successful_login):
            flow = self.module.FellowAidenConfigFlow()
            flow.hass = types.SimpleNamespace(session=object())
            flow._async_current_entries = lambda: [
                types.SimpleNamespace(
                    data={"brewer_id": "aiden-1"},
                    runtime_data=None,
                )
            ]

            result = await flow.async_step_user(
                {"email": "user@example.com", "password": "secret"}
            )

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["brewer_id"], "aiden-2")

    async def test_aborts_when_all_brewers_are_configured(self) -> None:
        devices = [
            {"id": "aiden-1", "displayName": "His"},
            {"id": "aiden-2", "displayName": "Hers"},
        ]

        async def successful_login(
            hass: object, email: str, password: str
        ) -> list[dict[str, str]]:
            del hass, email, password
            return devices

        with patch.object(self.module, "_try_login", new=successful_login):
            flow = self.module.FellowAidenConfigFlow()
            flow.hass = types.SimpleNamespace(session=object())
            flow._async_current_entries = lambda: [
                types.SimpleNamespace(
                    data={"brewer_id": device["id"]},
                    runtime_data=None,
                )
                for device in devices
            ]

            result = await flow.async_step_user(
                {"email": "user@example.com", "password": "secret"}
            )

        self.assertEqual(
            result,
            {"type": "abort", "reason": "all_brewers_configured"},
        )

    async def test_runtime_brewer_id_is_filtered_out(self) -> None:
        devices = [
            {"id": "aiden-1", "displayName": "His"},
            {"id": "aiden-2", "displayName": "Hers"},
        ]

        async def successful_login(
            hass: object, email: str, password: str
        ) -> list[dict[str, str]]:
            del hass, email, password
            return devices

        with patch.object(self.module, "_try_login", new=successful_login):
            flow = self.module.FellowAidenConfigFlow()
            flow.hass = types.SimpleNamespace(session=object())
            flow._async_current_entries = lambda: [
                types.SimpleNamespace(
                    data={},
                    runtime_data=types.SimpleNamespace(
                        api=types.SimpleNamespace(
                            get_brewer_id=lambda: "aiden-1"
                        )
                    ),
                )
            ]

            result = await flow.async_step_user(
                {"email": "user@example.com", "password": "secret"}
            )

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["brewer_id"], "aiden-2")

    async def test_legacy_same_account_entry_reserves_first_brewer(self) -> None:
        devices = [
            {"id": "aiden-1", "displayName": "His"},
            {"id": "aiden-2", "displayName": "Hers"},
        ]

        async def successful_login(
            hass: object, email: str, password: str
        ) -> list[dict[str, str]]:
            del hass, email, password
            return devices

        with patch.object(self.module, "_try_login", new=successful_login):
            flow = self.module.FellowAidenConfigFlow()
            flow.hass = types.SimpleNamespace(session=object())
            flow._async_current_entries = lambda: [
                types.SimpleNamespace(
                    data={"email": "USER@example.com"},
                    runtime_data=None,
                )
            ]

            result = await flow.async_step_user(
                {"email": "user@example.com", "password": "secret"}
            )

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["brewer_id"], "aiden-2")

    async def test_reauth_rejects_account_without_configured_brewer(
        self,
    ) -> None:
        async def successful_login(
            hass: object, email: str, password: str
        ) -> list[dict[str, str]]:
            del hass, email, password
            return [{"id": "aiden-1", "displayName": "His"}]

        with patch.object(self.module, "_try_login", new=successful_login):
            flow = self.module.FellowAidenConfigFlow()
            flow.hass = types.SimpleNamespace(session=object())
            await flow.async_step_reauth(
                {
                    "email": "user@example.com",
                    "brewer_id": "aiden-2",
                }
            )

            result = await flow.async_step_reauth_confirm(
                {"password": "new-secret"}
            )

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"]["base"], "unsupported_device")

    async def test_reconfigure_rejects_account_without_configured_brewer(
        self,
    ) -> None:
        async def successful_login(
            hass: object, email: str, password: str
        ) -> list[dict[str, str]]:
            del hass, email, password
            return [{"id": "aiden-1", "displayName": "His"}]

        with patch.object(self.module, "_try_login", new=successful_login):
            flow = self.module.FellowAidenConfigFlow()
            flow.hass = types.SimpleNamespace(session=object())
            flow._get_reconfigure_entry = lambda: types.SimpleNamespace(
                data={"brewer_id": "aiden-2"}
            )

            result = await flow.async_step_reconfigure(
                {
                    "email": "other@example.com",
                    "password": "secret",
                }
            )

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"]["base"], "unsupported_device")
