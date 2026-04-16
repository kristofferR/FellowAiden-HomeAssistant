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
