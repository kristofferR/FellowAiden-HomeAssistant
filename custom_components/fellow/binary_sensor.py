"""Binary sensor platform for Fellow Aiden."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_entity import FellowAidenBaseEntity
from .const import FellowAidenConfigEntry
from .coordinator import FellowAidenDataUpdateCoordinator
from .telemetry import (
    has_brew_error,
    has_unsynced_changes,
    is_brewing,
    is_missing_water,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# (api_key, device_class, translation_key, category, enabled_default)
BINARY_SENSORS = [
    ("brewing", BinarySensorDeviceClass.RUNNING, "brewing", None, True),
    ("carafePresent", None, "carafe_inserted", None, True),
    ("heaterOn", BinarySensorDeviceClass.HEAT, "heater", None, True),
    ("pumpOn", BinarySensorDeviceClass.RUNNING, "pump", None, True),
    ("lidClosed", BinarySensorDeviceClass.DOOR, "lid", None, True),
    ("missingWater", BinarySensorDeviceClass.PROBLEM, "missing_water", None, True),
    ("brewError", BinarySensorDeviceClass.PROBLEM, "brew_error", None, True),
    ("cleaning", BinarySensorDeviceClass.RUNNING, "cleaning", None, True),
    ("rinsing", BinarySensorDeviceClass.RUNNING, "rinsing", None, True),
    (
        "isConnected",
        BinarySensorDeviceClass.CONNECTIVITY,
        "cloud_connected",
        EntityCategory.DIAGNOSTIC,
        True,
    ),
    (
        "firmwareUpgradeRequired",
        BinarySensorDeviceClass.UPDATE,
        "firmware_update",
        EntityCategory.DIAGNOSTIC,
        True,
    ),
    (
        "unsynced",
        BinarySensorDeviceClass.PROBLEM,
        "unsynced_changes",
        EntityCategory.DIAGNOSTIC,
        False,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FellowAidenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fellow Aiden binary sensors."""
    coordinator = entry.runtime_data

    entities: list[BinarySensorEntity] = []
    for key, device_class, translation_key, category, enabled_default in BINARY_SENSORS:
        entities.append(
            FellowAidenBinarySensor(
                coordinator=coordinator,
                entry=entry,
                key=key,
                translation_key=translation_key,
                device_class=device_class,
                entity_category=category,
                enabled_default=enabled_default,
            )
        )

    if coordinator.push_manager:
        entities.append(FellowPushConnectionBinarySensor(coordinator, entry))

    async_add_entities(entities, True)


class FellowAidenBinarySensor(FellowAidenBaseEntity, BinarySensorEntity):
    """Binary sensor for a boolean value from the device config."""

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: FellowAidenConfigEntry,
        key: str,
        translation_key: str,
        device_class: BinarySensorDeviceClass | None,
        entity_category: EntityCategory | None,
        enabled_default: bool,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._key = key
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{entry.entry_id}-{key}"
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category
        self._attr_entity_registry_enabled_default = enabled_default

    @property
    def is_on(self) -> bool | None:
        """Return True if active.

        For lidClosed the API returns True when the lid is physically
        closed, but HA's DOOR class expects True to mean "open".
        We invert the value for that key.
        """
        data = self.coordinator.data or {}
        device_config = data.get("device_config", {})
        raw_value = device_config.get(self._key)

        if self._key == "brewing":
            return is_brewing(device_config)
        if self._key == "missingWater":
            return is_missing_water(device_config)
        if self._key == "brewError":
            return has_brew_error(device_config)
        if self._key == "unsynced":
            return has_unsynced_changes(device_config)
        if self._key == "lidClosed":
            if raw_value is None:
                return None
            return not raw_value

        return raw_value


class FellowPushConnectionBinarySensor(FellowAidenBaseEntity, BinarySensorEntity):
    """Report whether the account's Android cloud-push socket is connected."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "push_connected"

    def __init__(
        self,
        coordinator: FellowAidenDataUpdateCoordinator,
        entry: FellowAidenConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}-push-connected"

    @property
    def is_on(self) -> bool:
        """Return whether Google MCS has accepted the receiver login."""
        manager = self.coordinator.push_manager
        return bool(manager and manager.connected)

    @property
    def extra_state_attributes(self) -> dict[str, str | int]:
        """Expose useful connection diagnostics without receiver credentials."""
        manager = self.coordinator.push_manager
        if manager is None:
            return {"status": "disabled"}
        return {
            "status": manager.status.value,
            "messages_received": manager.message_count,
            "reconnections": manager.reconnect_count,
        }
