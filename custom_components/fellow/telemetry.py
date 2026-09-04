"""Helpers for Fellow v2 live device telemetry."""

from __future__ import annotations

import re
from typing import Any

MIN_REMOTE_START_FIRMWARE = (1, 5, 16)
_FIRMWARE_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:\+[0-9A-Za-z.-]+)?$")

BREW_PHASES = (
    "idle",
    "bloom",
    *(f"pulse_{number}" for number in range(1, 11)),
    "drip_finish",
    "paused",
    "brewing",
    "unknown",
)

_BREW_PHASE_CODES = {
    "b": "bloom",
    "d": "drip_finish",
    "pa": "paused",
}

DEVICE_EVENT_TYPES = (
    "brew_started",
    "brew_paused",
    "brew_resumed",
    "drip_finish",
    "brew_completed",
    "cleaning_started",
    "rinsing_started",
)


def brew_phase(device_config: dict[str, Any]) -> str:
    """Return a stable phase name from the v2 state object."""
    if "state" not in device_config:
        brewing = device_config.get("brewing")
        if brewing is True:
            return "brewing"
        if brewing is False:
            return "idle"
        return "unknown"

    state = device_config.get("state")
    if state is None:
        return "idle"
    if not isinstance(state, dict):
        return "unknown"

    value = state.get("value")
    if not isinstance(value, str):
        return "unknown"
    pulse_suffix = value[1:]
    if value.startswith("p") and pulse_suffix.isascii() and pulse_suffix.isdigit():
        pulse_number = int(pulse_suffix)
        if 1 <= pulse_number <= 10:
            return f"pulse_{pulse_number}"
    return _BREW_PHASE_CODES.get(value, "unknown")


def is_brewing(device_config: dict[str, Any]) -> bool | None:
    """Return live brew activity, preferring v2 state over the stale flag."""
    if "state" in device_config:
        return device_config.get("state") is not None
    value = device_config.get("brewing")
    return value if isinstance(value, bool) else None


def is_missing_water(device_config: dict[str, Any]) -> bool | None:
    """Combine top-level and live-state missing-water indicators."""
    top_level = device_config.get("missingWater")
    state = device_config.get("state")
    nested = state.get("missing_water") if isinstance(state, dict) else None
    if top_level is True or nested is True:
        return True
    if isinstance(top_level, bool):
        return top_level
    return nested if isinstance(nested, bool) else None


def has_brew_error(device_config: dict[str, Any]) -> bool | None:
    """Return whether the live state contains a brewer error."""
    if "state" not in device_config:
        return None
    state = device_config.get("state")
    if state is None:
        return False
    if not isinstance(state, dict):
        return None
    return state.get("error") is not None


def has_unsynced_changes(device_config: dict[str, Any]) -> bool | None:
    """Return whether the cloud reports queued device changes."""
    unsynced = device_config.get("unsynced")
    if isinstance(unsynced, list):
        return bool(unsynced)
    return None


def supports_remote_start(device_config: dict[str, Any]) -> bool:
    """Return whether firmware supports reliable remote brewing."""
    firmware = device_config.get("firmwareVersion")
    if not isinstance(firmware, str):
        return False
    match = _FIRMWARE_VERSION_RE.fullmatch(firmware.strip())
    if match is None:
        return False
    return tuple(int(part) for part in match.groups()) >= MIN_REMOTE_START_FIRMWARE


def can_start_brew(device_config: dict[str, Any]) -> bool:
    """Return whether reported state is safe for an Instant Brew start."""
    single_basket = device_config.get("singleBrewBasketPresent") is True
    batch_ready = (
        device_config.get("batchBrewBasketPresent") is True
        and device_config.get("carafePresent") is True
    )
    return bool(
        supports_remote_start(device_config)
        and device_config.get("isConnected") is True
        and is_brewing(device_config) is False
        and device_config.get("lidClosed") is True
        and is_missing_water(device_config) is False
        and device_config.get("cleaning") is False
        and device_config.get("rinsing") is False
        and (single_basket or batch_ready)
    )


def merge_event_telemetry(
    previous: dict[str, Any] | None, current: dict[str, Any]
) -> dict[str, Any]:
    """Retain definitive event state across partial cloud snapshots."""
    if previous is None:
        return dict(current)

    merged = dict(current)
    if is_brewing(current) is None:
        if "state" in previous:
            merged["state"] = previous.get("state")
        else:
            previous_brewing = previous.get("brewing")
            if isinstance(previous_brewing, bool):
                merged["brewing"] = previous_brewing

    if is_missing_water(current) is None:
        previous_missing_water = is_missing_water(previous)
        if previous_missing_water is not None:
            merged["missingWater"] = previous_missing_water

    for key in ("cleaning", "rinsing"):
        if not isinstance(current.get(key), bool) and isinstance(
            previous.get(key), bool
        ):
            merged[key] = previous[key]

    return merged


def device_events(
    previous: dict[str, Any] | None, current: dict[str, Any]
) -> list[str]:
    """Return meaningful device transitions between two live snapshots."""
    if previous is None:
        return []

    events: list[str] = []
    previous_active = is_brewing(previous)
    current_active = is_brewing(current)
    previous_phase = brew_phase(previous)
    current_phase = brew_phase(current)
    previous_paused = previous_phase == "paused" or is_missing_water(previous) is True
    current_paused = current_phase == "paused" or is_missing_water(current) is True

    if previous_active is False and current_active is True:
        events.append("brew_started")
    if current_active is True and not previous_paused and current_paused:
        events.append("brew_paused")
    if (
        previous_active is True
        and current_active is True
        and previous_paused
        and not current_paused
    ):
        events.append("brew_resumed")
    if current_phase == "drip_finish" and previous_phase != "drip_finish":
        events.append("drip_finish")
    if previous_active is True and current_active is False:
        events.append("brew_completed")
    if previous.get("cleaning") is not True and current.get("cleaning") is True:
        events.append("cleaning_started")
    if previous.get("rinsing") is not True and current.get("rinsing") is True:
        events.append("rinsing_started")

    return events
