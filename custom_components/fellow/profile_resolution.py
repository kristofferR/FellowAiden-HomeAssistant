"""Resolve the profile associated with the current or most recent brew."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProfileResolution:
    """A resolved profile and the evidence used to select it."""

    profile: dict[str, Any] | None
    method: str
    confidence: str

    @property
    def title(self) -> str | None:
        """Return the profile title when available."""
        if self.profile is None:
            return None
        title = self.profile.get("title")
        return title if isinstance(title, str) else None


def _positive_timestamp(value: Any) -> int | None:
    """Normalize a positive Unix timestamp from an API value."""
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return timestamp if timestamp > 0 else None


def _profile_by_id(
    profiles: list[dict[str, Any]], profile_id: Any
) -> dict[str, Any] | None:
    """Find a profile by its API identifier."""
    if not isinstance(profile_id, str) or not profile_id:
        return None
    return next(
        (profile for profile in profiles if profile.get("id") == profile_id),
        None,
    )


def resolve_current_profile(
    profiles: list[dict[str, Any]], device_config: dict[str, Any]
) -> ProfileResolution:
    """Resolve the active or most recently brewed profile.

    ``ibSelectedProfileId`` is the Instant Brew preset, not necessarily the
    profile used by the latest Guided Brew. Custom Guided Brew profiles are
    stamped with a ``lastUsedTime`` matching ``brewStartTime`` exactly.
    """
    if not profiles:
        return ProfileResolution(None, "unavailable", "low")

    active = _profile_by_id(profiles, device_config.get("brewingProfileId"))
    if active is not None:
        return ProfileResolution(active, "active_brew", "very_high")

    brew_start = _positive_timestamp(device_config.get("brewStartTime"))
    if brew_start is not None:
        exact_match = next(
            (
                profile
                for profile in profiles
                if _positive_timestamp(profile.get("lastUsedTime")) == brew_start
            ),
            None,
        )
        if exact_match is not None:
            return ProfileResolution(exact_match, "brew_start_time_match", "very_high")

    instant_brew = _profile_by_id(profiles, device_config.get("ibSelectedProfileId"))
    if instant_brew is not None:
        return ProfileResolution(instant_brew, "instant_brew_preset", "medium")

    recently_used = [
        (timestamp, profile)
        for profile in profiles
        if (timestamp := _positive_timestamp(profile.get("lastUsedTime"))) is not None
    ]
    if recently_used:
        return ProfileResolution(
            max(recently_used, key=lambda item: item[0])[1],
            "most_recent_profile",
            "high",
        )

    default_profile = next(
        (profile for profile in profiles if profile.get("isDefaultProfile")),
        None,
    )
    if default_profile is not None:
        return ProfileResolution(default_profile, "default_profile", "low_medium")

    return ProfileResolution(profiles[0], "first_available", "low")
