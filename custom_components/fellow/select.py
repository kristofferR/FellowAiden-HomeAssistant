"""Select entity to list brew profiles from Fellow Aiden."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_entity import FellowAidenBaseEntity
from .const import DOMAIN, FellowAidenConfigEntry
from .coordinator import FellowAidenDataUpdateCoordinator
from .profile_resolution import resolve_current_profile

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FellowAidenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entity listing all brew profiles."""
    coordinator = entry.runtime_data
    async_add_entities(
        [FellowAidenProfilesSelect(coordinator, entry)], update_before_add=True
    )


class FellowAidenProfilesSelect(FellowAidenBaseEntity, SelectEntity):
    """Dropdown showing available brew profiles.

    Selecting a profile from the UI is not supported by the Fellow API;
    async_select_option raises HomeAssistantError. Use the schedule or
    device controls to brew with a specific profile.
    """

    def __init__(
        self, coordinator: FellowAidenDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}-profile_select"
        self._attr_translation_key = "profiles"

    @property
    def options(self) -> list[str]:
        """Return profile titles."""
        data = self.coordinator.data
        if not data or "profiles" not in data:
            return []
        return [p.get("title", f"Profile {i}") for i, p in enumerate(data["profiles"])]

    @property
    def current_option(self) -> str | None:
        """Return the active profile, or the default, or the first one."""
        data = self.coordinator.data
        if not data or "profiles" not in data or not data["profiles"]:
            return None

        resolution = resolve_current_profile(
            data["profiles"], data.get("device_config", {})
        )
        return resolution.title

    async def async_select_option(self, option: str) -> None:
        """Raise error — the Fellow API doesn't support switching profiles remotely."""
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="profile_selection_not_supported",
        )
