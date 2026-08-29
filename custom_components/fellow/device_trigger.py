"""Device automation triggers for Fellow Aiden lifecycle events."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, Event, HassJob, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, EVENT_DEVICE
from .telemetry import DEVICE_EVENT_TYPES

TRIGGER_TYPES = DEVICE_EVENT_TYPES
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
    trigger_data = trigger_info["trigger_data"]
    job = HassJob(action)

    @callback
    def _handle_event(event: Event) -> None:
        if (
            event.data.get("config_entry_id") not in entry_ids
            or event.data.get("type") != trigger_type
        ):
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

    return hass.bus.async_listen(EVENT_DEVICE, _handle_event)
