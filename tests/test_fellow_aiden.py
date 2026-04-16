from __future__ import annotations

import asyncio
import unittest

from module_loader import load_fellow_aiden_module


class FakeResponse:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._payload = payload
        self.released = False

    async def json(self, content_type: object = None) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def text(self) -> str:
        return str(self._payload)

    async def read(self) -> bytes:
        return str(self._payload).encode()

    def release(self) -> None:
        self.released = True


class FakeSession:
    def __init__(self, responses: dict[tuple[str, str], list[object]]) -> None:
        self._responses = {
            key: list(value)
            for key, value in responses.items()
        }
        self.requests: list[tuple[str, str]] = []

    async def request(self, method: str, url: str, headers: object = None, **kwargs: object) -> object:
        del headers, kwargs
        key = (method.lower(), url)
        self.requests.append(key)
        queue = self._responses.get(key)
        if not queue:
            raise AssertionError(f"Unexpected request: {key}")
        result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FellowAidenDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.module, cleanup = load_fellow_aiden_module()
        self.addCleanup(cleanup)
        self.base_url = self.module.FellowAiden.BASE_URL

    def _api(self, responses: dict[tuple[str, str], list[object]]):
        session = FakeSession(responses)
        api = self.module.FellowAiden("user@example.com", "secret", session)
        return api, session

    async def test_selects_first_compatible_aiden_after_skipping_incompatible_device(self) -> None:
        api, _session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(200, {"accessToken": "token", "refreshToken": "refresh"})
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(
                        200,
                        [
                            {"id": "espresso-1", "displayName": "Espresso"},
                            {"id": "aiden-1", "displayName": "Aiden"},
                        ],
                    )
                ],
                ("get", f"{self.base_url}/devices/espresso-1/profiles"): [
                    FakeResponse(404, {"message": "Not found"})
                ],
                ("get", f"{self.base_url}/devices/aiden-1/profiles"): [
                    FakeResponse(200, [])
                ],
                ("get", f"{self.base_url}/devices/aiden-1/schedules"): [
                    FakeResponse(200, [])
                ],
            }
        )

        await api.authenticate()

        self.assertEqual(api.get_brewer_id(), "aiden-1")
        self.assertEqual(api.get_display_name(), "Aiden")
        self.assertEqual(await api.get_profiles(), [])
        self.assertEqual(await api.get_schedules(), [])

    async def test_empty_profiles_and_schedules_are_valid_for_supported_device(self) -> None:
        api, _session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(200, {"accessToken": "token", "refreshToken": "refresh"})
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(200, [{"id": "aiden-1", "displayName": "Aiden"}])
                ],
                ("get", f"{self.base_url}/devices/aiden-1/profiles"): [
                    FakeResponse(200, [])
                ],
                ("get", f"{self.base_url}/devices/aiden-1/schedules"): [
                    FakeResponse(200, [])
                ],
            }
        )

        await api.authenticate()

        self.assertEqual(await api.get_profiles(), [])
        self.assertEqual(await api.get_schedules(), [])

    async def test_raises_when_no_supported_devices_are_found(self) -> None:
        api, _session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(200, {"accessToken": "token", "refreshToken": "refresh"})
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(
                        200,
                        [
                            {"id": "espresso-1", "displayName": "Espresso"},
                            {"id": "unknown-1", "displayName": "Other"},
                        ],
                    )
                ],
                ("get", f"{self.base_url}/devices/espresso-1/profiles"): [
                    FakeResponse(404, {"message": "Not found"})
                ],
                ("get", f"{self.base_url}/devices/unknown-1/profiles"): [
                    FakeResponse(200, {"message": "wrong shape"})
                ],
            }
        )

        with self.assertRaises(self.module.FellowNoSupportedDeviceError):
            await api.authenticate()

    async def test_wraps_login_network_failures_as_connection_errors(self) -> None:
        api, _session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    self.module.aiohttp.ClientError("network down")
                ]
            }
        )

        with self.assertRaises(self.module.FellowConnectionError):
            await api.authenticate()

    async def test_wraps_discovery_timeouts_as_connection_errors(self) -> None:
        api, _session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(200, {"accessToken": "token", "refreshToken": "refresh"})
                ],
                ("get", f"{self.base_url}/devices"): [asyncio.TimeoutError()],
            }
        )

        with self.assertRaises(self.module.FellowConnectionError):
            await api.authenticate()

    async def test_raises_connection_error_after_final_transient_login_status(self) -> None:
        login_url = f"{self.base_url}/auth/login"
        api, session = self._api(
            {
                ("post", login_url): [
                    FakeResponse(503, {"message": "Service unavailable"})
                    for _ in range(self.module.FellowAiden._MAX_RETRIES + 1)
                ]
            }
        )

        with self.assertRaises(self.module.FellowConnectionError):
            await api.authenticate()

        self.assertEqual(
            session.requests,
            [("post", login_url)] * (self.module.FellowAiden._MAX_RETRIES + 1),
        )

    async def test_reuses_cached_brewer_when_it_remains_compatible(self) -> None:
        api, session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(200, {"accessToken": "token", "refreshToken": "refresh"})
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(
                        200,
                        [
                            {"id": "espresso-1", "displayName": "Espresso"},
                            {"id": "aiden-2", "displayName": "Second Aiden"},
                        ],
                    ),
                    FakeResponse(
                        200,
                        [
                            {"id": "aiden-1", "displayName": "First Aiden"},
                            {"id": "aiden-2", "displayName": "Second Aiden"},
                        ],
                    ),
                ],
                ("get", f"{self.base_url}/devices/espresso-1/profiles"): [
                    FakeResponse(404, {"message": "Not found"})
                ],
                ("get", f"{self.base_url}/devices/aiden-2/profiles"): [
                    FakeResponse(200, []),
                    FakeResponse(200, []),
                ],
                ("get", f"{self.base_url}/devices/aiden-2/schedules"): [
                    FakeResponse(200, []),
                    FakeResponse(200, []),
                ],
            }
        )

        await api.authenticate()
        session.requests.clear()

        await api.fetch_device()

        self.assertEqual(api.get_brewer_id(), "aiden-2")
        self.assertEqual(
            session.requests,
            [
                ("get", f"{self.base_url}/devices"),
                ("get", f"{self.base_url}/devices/aiden-2/profiles"),
                ("get", f"{self.base_url}/devices/aiden-2/schedules"),
            ],
        )
