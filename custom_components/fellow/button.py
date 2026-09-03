"""Button platform for Fellow Aiden controls."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_entity import FellowAidenBaseEntity
from .const import DOMAIN, FellowAidenConfigEntry
from .coordinator import FellowAidenDataUpdateCoordinator
from .telemetry import can_start_brew, supports_remote_start

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FellowAidenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fellow Aiden control buttons."""
    coordinator = entry.runtime_data
    async_add_entities([AidenRefreshButton(coordinator, entry)])

    start_brew_added = False

    def add_start_brew_when_supported() -> None:
        """Add remote start once compatible firmware is reported."""
        nonlocal start_brew_added
        device_config = (coordinator.data or {}).get("device_config", {})
        if start_brew_added or not supports_remote_start(device_config):
            return
        start_brew_added = True
        async_add_entities([AidenStartBrewButton(coordinator, entry)])

    add_start_brew_when_supported()
    if start_brew_added:
        return

    start_brew_unique_id = f"{entry.entry_id}-start-brew"
    entity_registry = er.async_get(hass)
    entity_id = entity_registry.async_get_entity_id(
        "button", DOMAIN, start_brew_unique_id
    )
    if entity_id:
        entity_registry.async_remove(entity_id)
    entry.async_on_unload(coordinator.async_add_listener(add_start_brew_when_supported))


class AidenStartBrewButton(FellowAidenBaseEntity, ButtonEntity):
    """Start the Instant Brew recipe already configured on the brewer."""

    _attr_translation_key = "start_brew"

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: FellowAidenConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}-start-brew"

    @property
    def available(self) -> bool:
        """Only offer remote start when reported device conditions are safe."""
        if not super().available:
            return False
        data = self.coordinator.data or {}
        return can_start_brew(data.get("device_config", {}))

    async def async_press(self) -> None:
        """Start Instant Brew remotely."""
        await self.coordinator.async_start_brew()


class AidenRefreshButton(FellowAidenBaseEntity, ButtonEntity):
    """Refresh all Fellow Aiden cloud data on demand."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "refresh"

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: FellowAidenConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}-refresh"

    async def async_press(self) -> None:
        """Refresh live state, profiles, and schedules."""
        self.coordinator.activate_fast_polling()
        await self.coordinator.async_refresh_with_resources(include_resources=True)
