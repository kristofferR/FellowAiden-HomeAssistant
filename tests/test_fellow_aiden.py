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
        self._responses = {key: list(value) for key, value in responses.items()}
        self.requests: list[tuple[str, str]] = []
        self.request_kwargs: list[dict[str, object]] = []

    async def request(
        self, method: str, url: str, headers: object = None, **kwargs: object
    ) -> object:
        key = (method.lower(), url)
        self.requests.append(key)
        self.request_kwargs.append({"headers": headers, **kwargs})
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

    def _api(
        self,
        responses: dict[tuple[str, str], list[object]],
        brewer_id: str | None = None,
    ):
        session = FakeSession(responses)
        api = self.module.FellowAiden(
            "user@example.com",
            "secret",
            session,
            brewer_id=brewer_id,
            timezone="Europe/Oslo",
        )
        return api, session

    async def test_selects_first_compatible_aiden_after_skipping_incompatible_device(
        self,
    ) -> None:
        api, _session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(
                        201, {"accessToken": "token", "refreshToken": "refresh"}
                    )
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
        self.assertEqual(
            _session.request_kwargs[0]["json"],
            {
                "email": "user@example.com",
                "password": "secret",
                "timezone": "Europe/Oslo",
            },
        )

    async def test_empty_profiles_and_schedules_are_valid_for_supported_device(
        self,
    ) -> None:
        api, _session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(
                        200, {"accessToken": "token", "refreshToken": "refresh"}
                    )
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
                    FakeResponse(
                        200, {"accessToken": "token", "refreshToken": "refresh"}
                    )
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
                    FakeResponse(
                        200, {"accessToken": "token", "refreshToken": "refresh"}
                    )
                ],
                ("get", f"{self.base_url}/devices"): [asyncio.TimeoutError()],
            }
        )

        with self.assertRaises(self.module.FellowConnectionError):
            await api.authenticate()

    async def test_raises_connection_error_after_final_transient_login_status(
        self,
    ) -> None:
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
                    FakeResponse(
                        200, {"accessToken": "token", "refreshToken": "refresh"}
                    )
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(
                        200,
                        [
                            {"id": "espresso-1", "displayName": "Espresso"},
                            {"id": "aiden-2", "displayName": "Second Aiden"},
                        ],
                    ),
                ],
                ("get", f"{self.base_url}/devices/espresso-1/profiles"): [
                    FakeResponse(404, {"message": "Not found"})
                ],
                ("get", f"{self.base_url}/devices/aiden-2/profiles"): [
                    FakeResponse(200, []),
                ],
                ("get", f"{self.base_url}/devices/aiden-2/schedules"): [
                    FakeResponse(200, []),
                ],
                ("get", f"{self.base_url}/devices/aiden-2"): [
                    FakeResponse(
                        200,
                        {
                            "id": "aiden-2",
                            "displayName": "Second Aiden",
                            "state": None,
                        },
                    )
                ],
            }
        )

        await api.authenticate()
        session.requests.clear()

        await api.fetch_device()

        self.assertEqual(api.get_brewer_id(), "aiden-2")
        self.assertEqual(
            session.requests,
            [("get", f"{self.base_url}/devices/aiden-2")],
        )
        self.assertEqual(session.request_kwargs[-1]["params"], {"dataType": "real"})

    async def test_discovers_every_compatible_aiden(self) -> None:
        api, _session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(
                        200,
                        {"accessToken": "token", "refreshToken": "refresh"},
                    )
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(
                        200,
                        [
                            {"id": "aiden-1", "displayName": "His"},
                            {"id": "espresso-1", "displayName": "Espresso"},
                            {"id": "aiden-2", "displayName": "Hers"},
                        ],
                    )
                ],
                ("get", f"{self.base_url}/devices/aiden-1/profiles"): [
                    FakeResponse(200, [])
                ],
                ("get", f"{self.base_url}/devices/aiden-1/schedules"): [
                    FakeResponse(200, [])
                ],
                ("get", f"{self.base_url}/devices/espresso-1/profiles"): [
                    FakeResponse(404, {"message": "Not found"})
                ],
                ("get", f"{self.base_url}/devices/aiden-2/profiles"): [
                    FakeResponse(200, [])
                ],
                ("get", f"{self.base_url}/devices/aiden-2/schedules"): [
                    FakeResponse(200, [])
                ],
            }
        )

        await api.authenticate(fetch_device=False)
        devices = await api.get_supported_devices()

        self.assertEqual(
            [(device["id"], device["displayName"]) for device in devices],
            [("aiden-1", "His"), ("aiden-2", "Hers")],
        )

    async def test_configured_brewer_is_pinned_across_refreshes(self) -> None:
        api, session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(
                        200,
                        {"accessToken": "token", "refreshToken": "refresh"},
                    )
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(
                        200,
                        [
                            {"id": "aiden-1", "displayName": "His"},
                            {"id": "aiden-2", "displayName": "Hers"},
                        ],
                    ),
                ],
                ("get", f"{self.base_url}/devices/aiden-2/profiles"): [
                    FakeResponse(200, []),
                ],
                ("get", f"{self.base_url}/devices/aiden-2/schedules"): [
                    FakeResponse(200, []),
                ],
                ("get", f"{self.base_url}/devices/aiden-2"): [
                    FakeResponse(200, {"id": "aiden-2", "displayName": "Hers"})
                ],
            },
            brewer_id="aiden-2",
        )

        await api.authenticate()
        await api.fetch_device()

        self.assertEqual(api.get_brewer_id(), "aiden-2")
        self.assertNotIn(
            ("get", f"{self.base_url}/devices/aiden-1/profiles"),
            session.requests,
        )

    async def test_configured_brewer_does_not_fall_back_to_another_device(
        self,
    ) -> None:
        api, session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(
                        200,
                        {"accessToken": "token", "refreshToken": "refresh"},
                    )
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(
                        200,
                        [{"id": "aiden-1", "displayName": "His"}],
                    )
                ],
            },
            brewer_id="aiden-2",
        )

        with self.assertRaises(self.module.FellowNoSupportedDeviceError):
            await api.authenticate()

        self.assertNotIn(
            ("get", f"{self.base_url}/devices/aiden-1/profiles"),
            session.requests,
        )

    async def test_incompatible_configured_brewer_does_not_fall_back(
        self,
    ) -> None:
        api, session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(
                        200,
                        {"accessToken": "token", "refreshToken": "refresh"},
                    )
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(
                        200,
                        [
                            {"id": "aiden-1", "displayName": "His"},
                            {"id": "aiden-2", "displayName": "Hers"},
                        ],
                    )
                ],
                ("get", f"{self.base_url}/devices/aiden-2/profiles"): [
                    FakeResponse(404, {"message": "Not found"})
                ],
            },
            brewer_id="aiden-2",
        )

        with self.assertRaises(self.module.FellowNoSupportedDeviceError):
            await api.authenticate()

        self.assertNotIn(
            ("get", f"{self.base_url}/devices/aiden-1/profiles"),
            session.requests,
        )

    async def test_pin_brewer_prevents_fallback_to_another_aiden(self) -> None:
        """A legacy entry that pins its discovered brewer must not fall back."""
        api, _session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(
                        200,
                        {"accessToken": "token", "refreshToken": "refresh"},
                    )
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(
                        200,
                        [{"id": "aiden-1", "displayName": "His"}],
                    ),
                ],
                ("get", f"{self.base_url}/devices/aiden-1/profiles"): [
                    FakeResponse(200, [])
                ],
                ("get", f"{self.base_url}/devices/aiden-1/schedules"): [
                    FakeResponse(200, [])
                ],
                ("get", f"{self.base_url}/devices/aiden-1"): [
                    FakeResponse(404, {"message": "Not found"})
                ],
            }
        )

        await api.authenticate()
        self.assertEqual(api.get_brewer_id(), "aiden-1")

        api.pin_brewer("aiden-1")

        # The pinned brewer disappeared from the account; the client must
        # report that rather than silently switching to the other Aiden.
        with self.assertRaises(self.module.FellowNoSupportedDeviceError):
            await api.fetch_device()

        self.assertEqual(api.get_brewer_id(), "aiden-1")

    async def test_v2_refresh_accepts_201_without_rotating_refresh_token(
        self,
    ) -> None:
        detail_url = f"{self.base_url}/devices/aiden-1"
        refresh_url = f"{self.base_url}/auth/refresh-token"
        api, session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(
                        201,
                        {"accessToken": "old-token", "refreshToken": "refresh"},
                    )
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
                ("get", detail_url): [
                    FakeResponse(401, {"message": "expired"}),
                    FakeResponse(200, {"id": "aiden-1", "state": None}),
                ],
                ("post", refresh_url): [
                    FakeResponse(201, {"accessToken": "new-token"})
                ],
            }
        )

        await api.authenticate()
        await api.fetch_device()

        refresh_index = session.requests.index(("post", refresh_url))
        self.assertEqual(
            session.request_kwargs[refresh_index]["json"],
            {"refreshToken": "refresh"},
        )
        self.assertEqual(
            session.request_kwargs[-1]["headers"]["Authorization"],
            "Bearer new-token",
        )

    async def test_refresh_resources_reloads_profiles_and_schedules(self) -> None:
        api, _session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(
                        201,
                        {"accessToken": "token", "refreshToken": "refresh"},
                    )
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(200, [{"id": "aiden-1", "displayName": "Aiden"}])
                ],
                ("get", f"{self.base_url}/devices/aiden-1/profiles"): [
                    FakeResponse(200, []),
                    FakeResponse(200, [{"id": "new", "title": "New"}]),
                ],
                ("get", f"{self.base_url}/devices/aiden-1/schedules"): [
                    FakeResponse(200, []),
                    FakeResponse(200, [{"id": "schedule"}]),
                ],
            }
        )

        await api.authenticate()
        result = await api.refresh_resources()

        self.assertEqual(result, (True, True))
        self.assertEqual(await api.get_profiles(), [{"id": "new", "title": "New"}])
        self.assertEqual(await api.get_schedules(), [{"id": "schedule"}])

    async def test_detail_refresh_preserves_discovered_inventory(self) -> None:
        api, _session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(
                        201,
                        {"accessToken": "token", "refreshToken": "refresh"},
                    )
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(
                        200,
                        [
                            {
                                "id": "aiden-1",
                                "displayName": "Aiden",
                                "serialNumber": "serial",
                            }
                        ],
                    )
                ],
                ("get", f"{self.base_url}/devices/aiden-1/profiles"): [
                    FakeResponse(200, [])
                ],
                ("get", f"{self.base_url}/devices/aiden-1/schedules"): [
                    FakeResponse(200, [])
                ],
                ("get", f"{self.base_url}/devices/aiden-1"): [
                    FakeResponse(200, {"id": "aiden-1", "state": {"value": "p1"}})
                ],
            }
        )

        await api.authenticate()
        await api.fetch_device()

        self.assertEqual(api.get_display_name(), "Aiden")
        self.assertEqual(api.get_device_config()["serialNumber"], "serial")
        self.assertEqual(api.get_device_config()["state"], {"value": "p1"})

    async def test_schedule_failure_does_not_discard_profile_refresh(self) -> None:
        api, _session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(
                        201,
                        {"accessToken": "token", "refreshToken": "refresh"},
                    )
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(200, [{"id": "aiden-1", "displayName": "Aiden"}])
                ],
                ("get", f"{self.base_url}/devices/aiden-1/profiles"): [
                    FakeResponse(200, []),
                    FakeResponse(200, [{"id": "new", "title": "New"}]),
                ],
                ("get", f"{self.base_url}/devices/aiden-1/schedules"): [
                    FakeResponse(200, [{"id": "old"}]),
                    FakeResponse(400, {"message": "Unavailable"}),
                ],
            }
        )

        await api.authenticate()
        result = await api.refresh_resources()

        self.assertEqual(result, (True, False))
        self.assertEqual(await api.get_profiles(), [{"id": "new", "title": "New"}])
        self.assertEqual(await api.get_schedules(), [{"id": "old"}])

    async def test_v2_profile_create_accepts_201_and_refreshes_cache(self) -> None:
        profiles_url = f"{self.base_url}/devices/aiden-1/profiles"
        profile = {
            "profileType": 0,
            "title": "V2 profile",
            "overallTemperature": 96,
        }
        api, session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(
                        201,
                        {"accessToken": "token", "refreshToken": "refresh"},
                    )
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(200, [{"id": "aiden-1", "displayName": "Aiden"}])
                ],
                ("get", profiles_url): [
                    FakeResponse(200, []),
                    FakeResponse(200, [{"id": "p1", **profile}]),
                ],
                ("get", f"{self.base_url}/devices/aiden-1/schedules"): [
                    FakeResponse(200, [])
                ],
                ("post", profiles_url): [FakeResponse(201, {"id": "p1", **profile})],
            }
        )

        await api.authenticate()
        created = await api.create_profile(profile)

        self.assertEqual(created["id"], "p1")
        create_index = session.requests.index(("post", profiles_url))
        self.assertEqual(session.request_kwargs[create_index]["json"], profile)
        self.assertEqual((await api.get_profiles())[0]["id"], "p1")

    async def test_v2_profile_delete_accepts_202(self) -> None:
        profiles_url = f"{self.base_url}/devices/aiden-1/profiles"
        api, _session = self._api(
            {
                ("post", f"{self.base_url}/auth/login"): [
                    FakeResponse(
                        201,
                        {"accessToken": "token", "refreshToken": "refresh"},
                    )
                ],
                ("get", f"{self.base_url}/devices"): [
                    FakeResponse(200, [{"id": "aiden-1", "displayName": "Aiden"}])
                ],
                ("get", profiles_url): [
                    FakeResponse(200, [{"id": "p1", "title": "Profile"}])
                ],
                ("get", f"{self.base_url}/devices/aiden-1/schedules"): [
                    FakeResponse(200, [])
                ],
                ("delete", f"{profiles_url}/p1"): [FakeResponse(202, {})],
            }
        )

        await api.authenticate()

        self.assertTrue(await api.delete_profile_by_id("p1"))

    async def test_registers_fcm_token_with_authenticated_v2_endpoint(self) -> None:
        push_url = f"{self.base_url}/firebase/notifications"
        api, session = self._api({("post", push_url): [FakeResponse(201, {})]})
        api._token = "access-token"

        await api.register_push_token("fcm-token")

        self.assertEqual(session.requests, [("post", push_url)])
        self.assertEqual(session.request_kwargs[0]["json"], {"fcmToken": "fcm-token"})
        self.assertEqual(
            session.request_kwargs[0]["headers"]["Authorization"],
            "Bearer access-token",
        )

    async def test_remote_start_uses_confirmed_no_body_route(self) -> None:
        start_url = f"{self.base_url}/devices/aiden-1/start"
        api, session = self._api(
            {
                ("patch", start_url): [
                    FakeResponse(200, {"id": "p1", "amountOfWater": 500})
                ]
            },
            brewer_id="aiden-1",
        )
        api._token = "access-token"

        result = await api.start_brew()

        self.assertEqual(result["amountOfWater"], 500)
        self.assertEqual(session.request_kwargs[0]["params"], {"confirm": "true"})
        self.assertNotIn("json", session.request_kwargs[0])

    async def test_remote_start_does_not_retry_transient_status(self) -> None:
        start_url = f"{self.base_url}/devices/aiden-1/start"
        api, session = self._api(
            {
                ("patch", start_url): [
                    FakeResponse(503, {"message": "Unavailable"}),
                    FakeResponse(200, {"amountOfWater": 500}),
                ]
            },
            brewer_id="aiden-1",
        )
        api._token = "access-token"

        with self.assertRaises(self.module.FellowApiError):
            await api.start_brew()

        self.assertEqual(session.requests, [("patch", start_url)])
