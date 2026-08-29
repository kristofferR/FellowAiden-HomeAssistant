"""Helpers for Fellow v2 live device telemetry."""

from __future__ import annotations

from typing import Any

BREW_PHASES = (
    "idle",
    "bloom",
    "pulse_1",
    "pulse_2",
    "pulse_3",
    "drip_finish",
    "paused",
    "brewing",
    "unknown",
)

_BREW_PHASE_CODES = {
    "b": "bloom",
    "p1": "pulse_1",
    "p2": "pulse_2",
    "p3": "pulse_3",
    "d": "drip_finish",
    "pa": "paused",
}


def brew_phase(device_config: dict[str, Any]) -> str:
    """Return a stable phase name from the v2 state object."""
    if "state" not in device_config:
        return "brewing" if device_config.get("brewing") else "idle"

    state = device_config.get("state")
    if state is None:
        return "idle"
    if not isinstance(state, dict):
        return "unknown"

    value = state.get("value")
    if not isinstance(value, str):
        return "unknown"
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


def has_brew_error(device_config: dict[str, Any]) -> bool:
    """Return whether the live state contains a brewer error."""
    state = device_config.get("state")
    return isinstance(state, dict) and state.get("error") is not None


def has_unsynced_changes(device_config: dict[str, Any]) -> bool | None:
    """Return whether the cloud reports queued device changes."""
    unsynced = device_config.get("unsynced")
    if isinstance(unsynced, list):
        return bool(unsynced)
    return None
