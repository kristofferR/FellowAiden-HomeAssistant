"""Device automation triggers for Fellow Aiden lifecycle events."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, Event, HassJob, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, EVENT_CLOUD_PUSH, EVENT_DEVICE
from .telemetry import DEVICE_EVENT_TYPES

CLOUD_NOTIFICATION = "cloud_notification"
TRIGGER_TYPES = (*DEVICE_EVENT_TYPES, CLOUD_NOTIFICATION)
TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES)}
)


def _entry_ids_for_device(hass: HomeAssistant, device_id: str) -> set[str]:
    """Return Fellow config entries attached to one HA device."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None or not any(domain == DOMAIN for domain, _ in device.identifiers):
        return set()
    fellow_entries = {
        entry.entry_id for entry in hass.config_entries.async_entries(DOMAIN)
    }
    return set(device.config_entries) & fellow_entries


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List all lifecycle triggers for a Fellow Aiden device."""
    if not _entry_ids_for_device(hass, device_id):
        return []
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in TRIGGER_TYPES
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a lifecycle trigger to the corresponding HA bus event."""
    entry_ids = _entry_ids_for_device(hass, config[CONF_DEVICE_ID])
    trigger_type = config[CONF_TYPE]
    event_name = (
        EVENT_CLOUD_PUSH if trigger_type == CLOUD_NOTIFICATION else EVENT_DEVICE
    )
    trigger_data = trigger_info["trigger_data"]
    job = HassJob(action)

    @callback
    def _handle_event(event: Event) -> None:
        if event_name == EVENT_CLOUD_PUSH:
            event_entry_ids = set(event.data.get("config_entry_ids", []))
            matches = bool(entry_ids & event_entry_ids)
        else:
            matches = (
                event.data.get("config_entry_id") in entry_ids
                and event.data.get("type") == trigger_type
            )
        if not matches:
            return
        hass.async_run_hass_job(
            job,
            {
                "trigger": {
                    **trigger_data,
                    **config,
                    "event": event.data,
                    "description": f"Fellow Aiden {trigger_type}",
                }
            },
            event.context,
        )

    return hass.bus.async_listen(event_name, _handle_event)
