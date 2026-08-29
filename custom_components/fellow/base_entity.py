"""Base entity for Fellow Aiden."""

from __future__ import annotations

from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class FellowAidenBaseEntity(CoordinatorEntity):
    """Base class for all Fellow Aiden entities, attaching them to one device."""

    _attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the brewer device registry."""
        data = self.coordinator.data or {}
        device_config = data.get("device_config", {})

        brewer_id = device_config.get("id") or getattr(self, "_entry_id", None)
        fw_version = device_config.get("firmwareVersion")
        wifi_mac = device_config.get("wifiMacAddress")
        bt_mac = device_config.get("btMacAddress")

        serial_number = device_config.get("serialNumber")
        model_id = device_config.get("sku")

        connections: set[tuple[str, str]] = set()
        if wifi_mac:
            connections.add((CONNECTION_NETWORK_MAC, wifi_mac))
        if bt_mac:
            connections.add((CONNECTION_BLUETOOTH, bt_mac))

        return DeviceInfo(
            identifiers={(DOMAIN, brewer_id)},
            name=data.get("brewer_name", "Fellow Aiden Brewer"),
            manufacturer="Fellow",
            model="Aiden",
            model_id=model_id,
            serial_number=serial_number,
            sw_version=fw_version,
            connections=connections,
        )
