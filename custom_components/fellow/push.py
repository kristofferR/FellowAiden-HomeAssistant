"""Account-scoped Fellow cloud push lifecycle for Home Assistant."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN, EVENT_CLOUD_PUSH, PUSH_MANAGERS
from .fcm import (
    FcmAuthenticationError,
    FcmClient,
    FcmCredentials,
    FcmError,
    FcmMessage,
)
from .fellow_aiden import FellowApiError, FellowAuthError, FellowConnectionError

if TYPE_CHECKING:
    from .coordinator import FellowAidenDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_STORE_VERSION = 1
_INITIAL_RETRY_SECONDS = 5.0
_MAX_RETRY_SECONDS = 300.0
_REFRESH_DEBOUNCE_SECONDS = 1.0


class PushStatus(StrEnum):
    """User-visible receiver state."""

    STOPPED = "stopped"
    REGISTERING = "registering"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RETRYING = "retrying"


class FellowPushManager:
    """Share one Android FCM receiver across entries for one Fellow account."""

    def __init__(self, hass: HomeAssistant, account_key: str) -> None:
        self.hass = hass
        self.account_key = account_key
        self.status = PushStatus.STOPPED
        self.last_message_at: datetime | None = None
        self.message_count = 0
        self.reconnect_count = 0
        self._coordinators: dict[str, FellowAidenDataUpdateCoordinator] = {}
        self._credentials: FcmCredentials | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass,
            _STORE_VERSION,
            f"{DOMAIN}.push.{account_key}",
            private=True,
        )
        self._task: asyncio.Task[None] | None = None
        self._refresh_task: asyncio.Task[None] | None = None
        self._refresh_pending = False
        self._retry_delay = _INITIAL_RETRY_SECONDS

    @property
    def connected(self) -> bool:
        """Return whether the Android MCS login is active."""
        return self.status is PushStatus.CONNECTED

    @property
    def entry_ids(self) -> list[str]:
        """Return config entries currently sharing this receiver."""
        return list(self._coordinators)

    @property
    def active(self) -> bool:
        """Return whether any config entries still use this receiver."""
        return bool(self._coordinators)

    def attach(
        self, entry_id: str, coordinator: FellowAidenDataUpdateCoordinator
    ) -> None:
        """Attach a config entry and expose receiver diagnostics to it."""
        self._coordinators[entry_id] = coordinator
        coordinator.set_push_manager(self)

    def detach(self, entry_id: str) -> None:
        """Detach one config entry."""
        coordinator = self._coordinators.pop(entry_id, None)
        if coordinator:
            coordinator.set_push_manager(None)

    def start(self) -> None:
        """Start the receiver without delaying config-entry setup."""
        if self._task is not None and not self._task.done():
            return
        self._task = self.hass.async_create_background_task(
            self._async_run(), f"{DOMAIN} FCM receiver {self.account_key}"
        )

    async def async_stop(self) -> None:
        """Cancel all account-owned work and persist delivery state."""
        for task in (self._task, self._refresh_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in (self._task, self._refresh_task) if task is not None),
            return_exceptions=True,
        )
        if self._credentials:
            await self._store.async_save(self._credentials.to_dict())
        self._task = None
        self._refresh_task = None
        self._refresh_pending = False
        self._set_status(PushStatus.STOPPED)

    def _set_status(self, status: PushStatus) -> None:
        if status is self.status:
            return
        self.status = status
        for coordinator in self._coordinators.values():
            coordinator.set_push_connected(self.connected)

    async def _async_register_with_fellow(self, token: str) -> None:
        for coordinator in self._coordinators.values():
            if coordinator.api:
                await coordinator.api.register_push_token(token)
                return
        raise RuntimeError("No authenticated Fellow API client is available")

    async def _async_connection_changed(self, connected: bool) -> None:
        if connected:
            self._retry_delay = _INITIAL_RETRY_SECONDS
        self._set_status(PushStatus.CONNECTED if connected else PushStatus.CONNECTING)

    async def _async_message(self, message: FcmMessage) -> None:
        """Publish the cloud event, persist its ID, and refresh device state."""
        self.last_message_at = datetime.now(UTC)
        self.message_count += 1
        if self._credentials:
            self._store.async_delay_save(self._credentials.to_dict, 5)

        self.hass.bus.async_fire(
            EVENT_CLOUD_PUSH,
            {
                "config_entry_ids": self.entry_ids,
                "category": message.category,
                "data": message.data,
            },
        )
        for coordinator in self._coordinators.values():
            coordinator.async_update_listeners()

        self._refresh_pending = True
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = self.hass.async_create_background_task(
                self._async_refresh_after_push(),
                f"{DOMAIN} refresh after cloud push {self.account_key}",
            )

    async def _async_refresh_after_push(self) -> None:
        while self._refresh_pending:
            self._refresh_pending = False
            await asyncio.sleep(_REFRESH_DEBOUNCE_SECONDS)
            results = await asyncio.gather(
                *(
                    coordinator.async_request_refresh()
                    for coordinator in self._coordinators.values()
                ),
                return_exceptions=True,
            )
            if any(isinstance(result, Exception) for result in results):
                _LOGGER.debug("A coordinator refresh after Fellow push failed")

    async def _async_retry_delay(self) -> None:
        self._set_status(PushStatus.RETRYING)
        await asyncio.sleep(
            self._retry_delay + random.uniform(0, self._retry_delay * 0.2)
        )
        self._retry_delay = min(self._retry_delay * 2, _MAX_RETRY_SECONDS)

    async def _async_register(self, client: FcmClient) -> bool:
        """Register Android credentials and the resulting Fellow token."""
        registration_failures = 0
        while self.active:
            self._set_status(PushStatus.REGISTERING)
            try:
                self._credentials = await client.async_register(self._credentials)
                await self._store.async_save(self._credentials.to_dict())
                await self._async_register_with_fellow(self._credentials.fcm_token)
                return True
            except asyncio.CancelledError:
                raise
            except (
                FcmError,
                FellowApiError,
                FellowAuthError,
                FellowConnectionError,
                RuntimeError,
            ) as err:
                log = _LOGGER.warning if registration_failures == 0 else _LOGGER.debug
                log(
                    "Unable to register Fellow cloud push; polling remains active: %s",
                    err,
                )
                registration_failures += 1
                await self._async_retry_delay()
        return False

    async def _async_run(self) -> None:
        """Register once, then reconnect the long-lived MCS socket as needed."""
        stored = await self._store.async_load()
        self._credentials = FcmCredentials.from_dict(stored)
        client = FcmClient(async_get_clientsession(self.hass))
        while self.active:
            if not await self._async_register(client):
                return

            while self.active and self._credentials:
                self._set_status(PushStatus.CONNECTING)
                try:
                    await client.async_listen(
                        self._credentials,
                        self._async_message,
                        self._async_connection_changed,
                    )
                except asyncio.CancelledError:
                    raise
                except FcmAuthenticationError as err:
                    self.reconnect_count += 1
                    _LOGGER.warning(
                        "Fellow cloud push credentials were rejected; registering again: %s",
                        err,
                    )
                    self._credentials = None
                    await self._store.async_save({})
                    await self._async_retry_delay()
                    break
                except FcmError as err:
                    self.reconnect_count += 1
                    log = (
                        _LOGGER.warning if self.reconnect_count == 1 else _LOGGER.debug
                    )
                    log(
                        "Fellow cloud push disconnected; polling remains active: %s",
                        err,
                    )
                    await self._async_retry_delay()


def _account_key(email: str) -> str:
    """Return a stable private-storage key without retaining the email."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]


def attach_push(
    hass: HomeAssistant,
    entry_id: str,
    email: str,
    coordinator: FellowAidenDataUpdateCoordinator,
) -> FellowPushManager:
    """Attach an entry to its account receiver and start it if needed."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    managers: dict[str, FellowPushManager] = domain_data.setdefault(PUSH_MANAGERS, {})
    account_key = _account_key(email)
    manager = managers.get(account_key)
    if manager is None:
        manager = FellowPushManager(hass, account_key)
        managers[account_key] = manager
    manager.attach(entry_id, coordinator)
    manager.start()
    return manager


async def async_detach_push(hass: HomeAssistant, entry_id: str) -> None:
    """Detach an entry and stop the shared receiver when no users remain."""
    managers: dict[str, FellowPushManager] = hass.data.get(DOMAIN, {}).get(
        PUSH_MANAGERS, {}
    )
    for account_key, manager in list(managers.items()):
        if entry_id not in manager.entry_ids:
            continue
        manager.detach(entry_id)
        if not manager.active:
            await manager.async_stop()
            managers.pop(account_key, None)
        return
