"""Async Fellow object to interact with Aiden brewer."""
from __future__ import annotations

import asyncio
import logging
import re
import ssl
from difflib import SequenceMatcher
from typing import Any

import aiohttp
from pydantic import ValidationError

from .profile import CoffeeProfile
from .schedule import CoffeeSchedule


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


class FellowAuthError(Exception):
    """Raised when Fellow API authentication fails (bad credentials)."""


class FellowConnectionError(Exception):
    """Raised when a Fellow API request fails due to connectivity issues."""


class FellowNoSupportedDeviceError(Exception):
    """Raised when the account has no compatible Fellow Aiden brewer."""


class _IncompatibleDeviceError(Exception):
    """Raised when a device candidate does not expose Aiden endpoints."""


class FellowAiden:
    """Async Fellow object to interact with Aiden brewer.

    Requires an ``aiohttp.ClientSession`` (e.g. from Home Assistant's
    ``async_get_clientsession``).  Call :meth:`authenticate` after
    construction to perform the initial login and device fetch.
    """

    LOGGER_NAME = "custom_components.fellow.fellow_aiden.api"
    BASE_URL = "https://l8qtmnc692.execute-api.us-west-2.amazonaws.com/v1"
    API_AUTH = "/auth/login"
    API_AUTH_REFRESH = "/auth/refresh"
    API_DEVICES = "/devices"
    API_DEVICE = "/devices/{id}"
    API_SCHEDULES = "/devices/{id}/schedules"
    API_SCHEDULE = "/devices/{id}/schedules/{sid}"
    API_PROFILES = "/devices/{id}/profiles"
    API_PROFILE = "/devices/{id}/profiles/{pid}"
    API_PROFILE_SHARE = "/devices/{id}/profiles/{pid}/share"
    API_SHARED_PROFILE = "/shared/{bid}"
    HEADERS = {
        "User-Agent": "Fellow/5 CFNetwork/1568.300.101 Darwin/24.2.0",
    }
    SERVER_SIDE_PROFILE_FIELDS = [
        "id",
        "createdAt",
        "deletedAt",
        "lastUsedTime",
        "sharedFrom",
        "isDefaultProfile",
        "instantBrew",
        "folder",
        "duration",
        "lastGBQuantity",
    ]

    _RETRY_STATUSES = frozenset({408, 500, 501, 502, 503, 504})
    _TRANSIENT_HTTP_STATUSES = frozenset({408, 429, 500, 501, 502, 503, 504})
    _INCOMPATIBLE_DEVICE_STATUSES = frozenset({400, 404, 405, 422})
    _MAX_RETRIES = 3

    def __init__(
        self, email: str, password: str, session: aiohttp.ClientSession
    ) -> None:
        """Store credentials and session.  Call ``authenticate()`` to log in."""
        self._log = logging.getLogger(self.LOGGER_NAME)
        self._auth = False
        self._token: str | None = None
        self._refresh_token: str | None = None
        self._email = email
        self._password = password
        self._device_config: dict[str, Any] | None = None
        self._brewer_id: str | None = None
        self._profiles: list[dict[str, Any]] | None = None
        self._schedules: list[dict[str, Any]] | None = None
        self._session = session

    # -- HTTP helpers -------------------------------------------------------

    def _build_headers(self, authenticated: bool = True) -> dict[str, str]:
        """Return request headers, optionally including the Bearer token."""
        headers = dict(self.HEADERS)
        if authenticated and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _request(
        self,
        method: str,
        url: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """HTTP request with automatic retries on server errors."""
        headers = self._build_headers(authenticated)

        response: aiohttp.ClientResponse | None = None
        for attempt in range(self._MAX_RETRIES + 1):
            try:
                response = await self._session.request(
                    method, url, headers=headers, **kwargs
                )
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                ssl.SSLError,
            ) as err:
                raise FellowConnectionError(
                    f"Request failed for {method.upper()} {url}: {err}"
                ) from err
            if response.status not in self._TRANSIENT_HTTP_STATUSES:
                return response
            if response.status not in self._RETRY_STATUSES or attempt == self._MAX_RETRIES:
                parsed = await self._parse_response(response)
                raise FellowConnectionError(
                    f"Request failed for {method.upper()} {url} ({response.status}): {parsed}"
                )
            response.release()
            await asyncio.sleep(min(2 ** attempt, 8))
            self._log.debug(
                "Retry %d/%d for %s %s (status %s)",
                attempt + 1,
                self._MAX_RETRIES,
                method.upper(),
                url,
                response.status,
            )
        return response  # type: ignore[return-value]

    async def _request_with_reauth(
        self, method: str, url: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Send a request and retry once after refreshing auth on HTTP 401."""
        response = await self._request(method, url, **kwargs)
        if response.status == 401:
            self._log.debug("Token expired, attempting refresh")
            refreshed = await self._refresh_auth()
            if refreshed:
                self._log.debug("Token refresh successful")
                response.release()
                response = await self._request(method, url, **kwargs)
                if response.status == 401:
                    self._log.debug(
                        "Still 401 after token refresh, falling back to full re-login"
                    )
                    response.release()
                    await self._do_auth(fetch_device=False)
                    response = await self._request(method, url, **kwargs)
            else:
                self._log.debug("Token refresh failed, falling back to full re-login")
                response.release()
                await self._do_auth(fetch_device=False)
                response = await self._request(method, url, **kwargs)
            if response.status == 401:
                self._log.warning(
                    "Still unauthorized after re-authentication — credentials may be invalid"
                )
                response.release()
                raise FellowAuthError(
                    "Still unauthorized after re-authentication — credentials may be invalid"
                )
        return response

    async def _parse_response(
        self, response: aiohttp.ClientResponse
    ) -> Any:
        """Parse a response body as JSON, falling back to raw text."""
        try:
            return await response.json(content_type=None)
        except (ValueError, aiohttp.ContentTypeError):
            text = (await response.text()).strip()
            if text:
                return {"raw": text}
            return {}

    async def _ensure_success(
        self, response: aiohttp.ClientResponse, action: str
    ) -> None:
        """Raise a descriptive error when a response is not HTTP 2xx."""
        if 200 <= response.status < 300:
            return
        parsed = await self._parse_response(response)
        raise Exception(f"{action} failed ({response.status}): {parsed}")

    # -- Authentication -----------------------------------------------------

    async def authenticate(self) -> None:
        """Authenticate and fetch initial device data."""
        await self._do_auth(fetch_device=True)

    async def _refresh_auth(self) -> bool:
        """Attempt to refresh the access token using the stored refresh token.

        Returns True on success, False on any failure (allowing fallback to full login).
        """
        if not self._refresh_token:
            return False
        try:
            refresh_url = self.BASE_URL + self.API_AUTH_REFRESH
            response = await self._request(
                "post",
                refresh_url,
                authenticated=False,
                json={"refreshToken": self._refresh_token},
            )
        except Exception:
            self._log.debug("Refresh token request failed", exc_info=True)
            return False

        if response.status != 200:
            self._log.debug("Refresh endpoint returned %s", response.status)
            response.release()
            return False
        parsed = await self._parse_response(response)
        if "accessToken" not in parsed:
            self._log.debug("Refresh response missing accessToken")
            return False
        self._token = parsed["accessToken"]
        if "refreshToken" in parsed:
            self._refresh_token = parsed["refreshToken"]
        return True

    async def _do_auth(self, fetch_device: bool = False) -> None:
        """Perform email/password authentication."""
        self._log.debug("Authenticating user")
        login_url = self.BASE_URL + self.API_AUTH
        auth_payload = {"email": self._email, "password": self._password}
        response = await self._request(
            "post", login_url, authenticated=False, json=auth_payload,
        )
        if response.status in (400, 401, 403):
            response.release()
            raise FellowAuthError("Email or password incorrect.")

        await self._ensure_success(response, "Authentication")
        parsed = await self._parse_response(response)
        if "accessToken" not in parsed or "refreshToken" not in parsed:
            raise Exception(f"Authentication response missing tokens: {parsed}")

        self._log.debug("Authentication successful")
        self._token = parsed["accessToken"]
        self._refresh_token = parsed["refreshToken"]
        self._auth = True
        if fetch_device:
            await self._fetch_device()

    # -- Device & data fetching ---------------------------------------------

    async def _fetch_device(self) -> None:
        """Fetch device info from the API."""
        self._log.debug("Fetching device for account")
        device_url = self.BASE_URL + self.API_DEVICES
        response = await self._request_with_reauth(
            "get", device_url, params={"dataType": "real"}
        )
        await self._ensure_success(response, "Device fetch")

        parsed = await self._parse_response(response)
        self._log.debug(parsed)
        if not isinstance(parsed, list):
            raise Exception(f"Unexpected device response payload: {parsed}")
        device_candidates = [
            device for device in parsed if isinstance(device, dict)
        ]
        if not device_candidates:
            raise FellowNoSupportedDeviceError(
                "No supported Fellow Aiden brewer was found on this account."
            )

        for candidate in self._ordered_device_candidates(device_candidates):
            try:
                brewer_id, profiles, schedules = await self._probe_device(candidate)
            except _IncompatibleDeviceError as err:
                self._log.debug("Skipping incompatible device candidate: %s", err)
                continue

            self._device_config = candidate
            self._brewer_id = brewer_id
            self._profiles = profiles
            self._schedules = schedules

            self._log.debug("Brewer ID: %s", self._brewer_id)
            self._log.debug("Device and profile information set")
            return

        raise FellowNoSupportedDeviceError(
            "No supported Fellow Aiden brewer was found on this account."
        )

    async def fetch_device(self) -> None:
        """Public method to re-fetch device data from the cloud."""
        await self._fetch_device()

    async def get_profiles(self) -> list[dict[str, Any]]:
        """Return profiles, fetching from API if not cached."""
        if self._profiles is None:
            self._log.debug("Fetching profiles")
            profiles_url = self.BASE_URL + self.API_PROFILES.format(
                id=self._brewer_id
            )
            self._profiles = await self._fetch_list_resource(
                profiles_url, "Profile fetch"
            )
        return self._profiles

    async def get_schedules(self) -> list[dict[str, Any]]:
        """Return schedules, fetching from API if not cached."""
        if self._schedules is None:
            self._log.debug("Fetching schedules")
            schedules_url = self.BASE_URL + self.API_SCHEDULES.format(
                id=self._brewer_id
            )
            self._schedules = await self._fetch_list_resource(
                schedules_url, "Schedule fetch"
            )
        return self._schedules

    def get_device_config(self) -> dict[str, Any] | None:
        """Return the cached device config."""
        return self._device_config

    def get_display_name(self) -> str | None:
        """Return the brewer display name from cached config."""
        if self._device_config is None:
            return None
        return self._device_config.get("displayName")

    def get_brewer_id(self) -> str | None:
        """Return the brewer ID."""
        return self._brewer_id

    # -- Internal helpers ---------------------------------------------------

    def _ordered_device_candidates(
        self, devices: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Return devices ordered with the cached brewer first when possible."""
        if not self._brewer_id:
            return devices

        preferred = [
            device for device in devices if device.get("id") == self._brewer_id
        ]
        remaining = [
            device for device in devices if device.get("id") != self._brewer_id
        ]
        return preferred + remaining

    async def _fetch_list_resource(
        self, url: str, action: str
    ) -> list[dict[str, Any]]:
        """Fetch a list payload from the Fellow API."""
        response = await self._request_with_reauth("get", url)
        await self._ensure_success(response, action)

        parsed = await self._parse_response(response)
        if not isinstance(parsed, list) or any(
            not isinstance(item, dict) for item in parsed
        ):
            raise Exception(f"Unexpected {action.lower()} payload: {parsed}")

        self._log.debug(parsed)
        return parsed

    async def _probe_list_resource(
        self, brewer_id: str, url: str, action: str
    ) -> list[dict[str, Any]]:
        """Probe a candidate device endpoint and treat non-Aiden shapes as incompatible."""
        response = await self._request_with_reauth("get", url)

        if response.status in (401, 403):
            parsed = await self._parse_response(response)
            raise FellowAuthError(
                f"{action} unauthorized for device {brewer_id} ({response.status}): {parsed}"
            )
        if response.status in self._TRANSIENT_HTTP_STATUSES:
            parsed = await self._parse_response(response)
            raise FellowConnectionError(
                f"{action} failed for device {brewer_id} ({response.status}): {parsed}"
            )
        if response.status in self._INCOMPATIBLE_DEVICE_STATUSES:
            response.release()
            raise _IncompatibleDeviceError(
                f"Device {brewer_id} does not support {action.lower()} ({response.status})"
            )
        if not 200 <= response.status < 300:
            parsed = await self._parse_response(response)
            raise _IncompatibleDeviceError(
                f"Device {brewer_id} returned {response.status} for {action.lower()}: {parsed}"
            )

        parsed = await self._parse_response(response)
        if not isinstance(parsed, list):
            raise _IncompatibleDeviceError(
                f"Device {brewer_id} returned non-list {action.lower()} payload: {parsed}"
            )
        if any(not isinstance(item, dict) for item in parsed):
            raise _IncompatibleDeviceError(
                f"Device {brewer_id} returned invalid {action.lower()} payload: {parsed}"
            )
        return parsed

    async def _probe_device(
        self, candidate: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """Return cached data for a compatible Aiden candidate."""
        brewer_id = candidate.get("id")
        if not isinstance(brewer_id, str) or not brewer_id:
            raise _IncompatibleDeviceError(
                f"Device response missing required id field: {candidate}"
            )

        profiles_url = self.BASE_URL + self.API_PROFILES.format(id=brewer_id)
        schedules_url = self.BASE_URL + self.API_SCHEDULES.format(id=brewer_id)
        profiles = await self._probe_list_resource(
            brewer_id, profiles_url, "Profile fetch"
        )
        schedules = await self._probe_list_resource(
            brewer_id, schedules_url, "Schedule fetch"
        )
        return brewer_id, profiles, schedules

    async def _get_profile_ids(self) -> list[str]:
        """Return a list of profile IDs with titles."""
        profiles = await self.get_profiles()
        return [f"{p['id']} ({p['title']})" for p in profiles]

    async def _is_valid_profile_id(self, pid: str) -> bool:
        """Check if a profile ID is valid."""
        profiles = await self.get_profiles()
        return any(pid == p["id"] for p in profiles)

    async def _get_schedule_ids(self) -> list[str]:
        """Return a list of schedule IDs."""
        schedules = await self.get_schedules()
        return [str(s["id"]) for s in schedules]

    async def _is_valid_schedule_id(self, sid: str) -> bool:
        """Check if a schedule ID is valid."""
        schedules = await self.get_schedules()
        return any(sid == str(s["id"]) for s in schedules)

    # -- Profile operations -------------------------------------------------

    async def get_profile_by_title(
        self, title: str, fuzzy: bool = False
    ) -> dict[str, Any] | None:
        """Find a profile by title."""
        profiles = await self.get_profiles()
        for profile in profiles:
            if fuzzy and similar(profile["title"].lower(), title.lower()) > 0.65:
                return profile
            if profile["title"].lower() == title.lower():
                return profile
        return None

    async def parse_brewlink_url(self, link: str) -> dict[str, Any]:
        """Extract profile information from a shared brew link."""
        self._log.debug("Parsing shared brew link")
        pattern = r"(?:.*?/p/)?([a-zA-Z0-9]+)/?$"
        match = re.search(pattern, link)
        if not match:
            raise ValueError("Invalid profile URL or ID format")
        brew_id = match.group(1)
        self._log.debug("Brew ID: %s", brew_id)
        shared_url = self.BASE_URL + self.API_SHARED_PROFILE.format(bid=brew_id)
        response = await self._request_with_reauth("get", shared_url)
        if response.status == 404:
            response.release()
            raise ValueError(f"Failed to fetch profile (ID: {brew_id})")

        await self._ensure_success(
            response, f"Shared profile fetch (ID: {brew_id})"
        )
        parsed = await self._parse_response(response)
        if not isinstance(parsed, dict):
            raise ValueError(
                f"Unexpected shared profile payload for ID {brew_id}: {parsed}"
            )

        for field in self.SERVER_SIDE_PROFILE_FIELDS:
            parsed.pop(field, None)
        self._log.debug("Profile fetched: %s", parsed)
        return parsed

    async def create_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new brew profile."""
        self._log.debug("Checking brew profile: %s", data)
        try:
            CoffeeProfile.model_validate(data)
        except ValidationError as err:
            self._log.error("Brew profile format was invalid: %s", err)
            raise ValueError(f"Brew profile format was invalid: {err}") from err

        if "id" in data:
            raise Exception(
                "Candidate profiles must be free of server derived fields."
            )

        self._log.debug("Brew profile passed checks")
        profile_url = self.BASE_URL + self.API_PROFILES.format(id=self._brewer_id)
        response = await self._request_with_reauth("post", profile_url, json=data)
        await self._ensure_success(response, "Profile creation")

        parsed = await self._parse_response(response)
        if not isinstance(parsed, dict):
            raise Exception(f"Unexpected profile creation payload: {parsed}")
        if "id" not in parsed:
            raise Exception(f"Error in processing: {parsed}")

        await self._fetch_device()
        self._log.debug("Brew profile created: %s", parsed)
        return parsed

    async def update_profile(
        self, profile_id: str, data: dict[str, Any]
    ) -> bool:
        """Update an existing profile by ID."""
        self._log.debug("Updating brew profile %s: %s", profile_id, data)
        try:
            CoffeeProfile.model_validate(data)
        except ValidationError as err:
            self._log.error("Brew profile format was invalid: %s", err)
            raise ValueError(f"Brew profile format was invalid: {err}") from err

        if not await self._is_valid_profile_id(profile_id):
            ids = await self._get_profile_ids()
            raise Exception(
                f"Profile with ID {profile_id} does not exist. Valid profiles: {ids}"
            )

        for field in self.SERVER_SIDE_PROFILE_FIELDS:
            data.pop(field, None)

        update_url = self.BASE_URL + self.API_PROFILE.format(
            id=self._brewer_id, pid=profile_id
        )
        self._log.debug("Update URL: %s", update_url)
        response = await self._request_with_reauth("patch", update_url, json=data)
        await self._ensure_success(response, f"Profile update ({profile_id})")

        await self._fetch_device()
        self._log.debug("Profile %s updated successfully", profile_id)
        return True

    async def create_profile_from_link(self, link: str) -> dict[str, Any]:
        """Create a profile from a shared brew link."""
        self._log.debug("Creating profile from link")
        data = await self.parse_brewlink_url(link)
        return await self.create_profile(data)

    async def generate_share_link(self, pid: str) -> str:
        """Generate a share link for a profile."""
        self._log.debug("Generating share link")
        share_url = self.BASE_URL + self.API_PROFILE_SHARE.format(
            id=self._brewer_id, pid=pid
        )
        self._log.debug("Share URL: %s", share_url)
        response = await self._request_with_reauth("post", share_url)
        await self._ensure_success(response, f"Share link generation ({pid})")

        parsed = await self._parse_response(response)
        if "link" not in parsed:
            raise Exception(f"Error in processing: {parsed}")

        self._log.debug("Share link generated: %s", parsed)
        return parsed["link"]

    async def delete_profile_by_id(self, pid: str) -> bool:
        """Delete a profile by ID."""
        self._log.debug("Deleting profile")
        delete_url = self.BASE_URL + self.API_PROFILE.format(
            id=self._brewer_id, pid=pid
        )
        self._log.debug(delete_url)
        response = await self._request_with_reauth("delete", delete_url)
        await self._ensure_success(response, f"Profile deletion ({pid})")
        self._profiles = None

        self._log.debug("Profile deleted")
        return True

    # -- Schedule operations ------------------------------------------------

    async def create_schedule(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new brew schedule."""
        self._log.debug("Checking schedule: %s", data)
        try:
            CoffeeSchedule.model_validate(data)
        except ValidationError as err:
            self._log.error("Brew schedule format was invalid: %s", err)
            raise ValueError(
                f"Brew schedule format was invalid: {err}"
            ) from err

        if "id" in data:
            raise Exception(
                "Candidate schedules must be free of server derived fields."
            )

        self._log.debug("Brew schedule passed checks")
        schedule_url = self.BASE_URL + self.API_SCHEDULES.format(
            id=self._brewer_id
        )
        response = await self._request_with_reauth(
            "post", schedule_url, json=data
        )
        await self._ensure_success(response, "Schedule creation")

        parsed = await self._parse_response(response)
        if not isinstance(parsed, dict):
            raise Exception(f"Unexpected schedule creation payload: {parsed}")
        if "id" not in parsed:
            message = parsed.get("message", "Unable to get error message.")
            if "Profile could not be found" in message:
                ids = await self._get_profile_ids()
                message += f" Valid profiles: {ids}"
            raise Exception(f"Error in processing: {message}")

        await self._fetch_device()
        self._log.debug("Brew schedule created: %s", parsed)
        return parsed

    async def delete_schedule_by_id(self, sid: str) -> bool:
        """Delete a schedule by ID."""
        self._log.debug("Deleting schedule")
        if not await self._is_valid_schedule_id(sid):
            ids = await self._get_schedule_ids()
            raise Exception(
                f"Schedule does not exist. Valid schedules: {ids}"
            )
        delete_url = self.BASE_URL + self.API_SCHEDULE.format(
            id=self._brewer_id, sid=sid
        )
        self._log.debug(delete_url)
        response = await self._request_with_reauth("delete", delete_url)
        await self._ensure_success(response, f"Schedule deletion ({sid})")
        self._schedules = None

        self._log.debug("Schedule deleted")
        return True

    async def adjust_setting(self, setting: str, value: Any) -> bytes:
        """Adjust a device setting."""
        patch_url = self.BASE_URL + self.API_DEVICE.format(id=self._brewer_id)
        self._log.debug("Patch URL: %s", patch_url)
        response = await self._request_with_reauth(
            "patch", patch_url, json={setting: value}
        )
        await self._ensure_success(
            response, f"Device setting update ({setting})"
        )
        return await response.read()

    async def toggle_schedule(self, sid: str, enabled: bool) -> bool:
        """Enable or disable a schedule."""
        if not await self._is_valid_schedule_id(sid):
            ids = await self._get_schedule_ids()
            raise Exception(
                f"Schedule does not exist. Valid schedules: {ids}"
            )
        patch_url = self.BASE_URL + self.API_SCHEDULE.format(
            id=self._brewer_id, sid=sid
        )
        self._log.debug("Patch URL: %s", patch_url)
        response = await self._request_with_reauth(
            "patch", patch_url, json={"enabled": enabled}
        )
        await self._ensure_success(response, f"Schedule toggle ({sid})")
        self._schedules = None
        return True
