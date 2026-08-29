"""Button platform for Fellow Aiden controls."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_entity import FellowAidenBaseEntity
from .const import FellowAidenConfigEntry
from .coordinator import FellowAidenDataUpdateCoordinator
from .telemetry import can_start_brew

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FellowAidenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fellow Aiden control buttons."""
    async_add_entities([AidenStartBrewButton(entry.runtime_data, entry)])


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
