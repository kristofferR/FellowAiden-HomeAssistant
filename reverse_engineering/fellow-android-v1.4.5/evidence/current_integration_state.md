# Current Home Assistant Integration State

- Domain: `fellow` (`custom_components/fellow/manifest.json` reports `iot_class` `cloud_polling`).
- Current entity platforms: `sensor`, `binary_sensor`, and `select`.
- Vendored API client files exist under `custom_components/fellow/fellow_aiden/` for device, profile, and schedule handling.
- Registered Home Assistant services:
  - `create_profile`
  - `delete_profile`
  - `create_schedule`
  - `delete_schedule`
  - `toggle_schedule`
  - `list_profiles`
  - `get_profile_details`
  - `reset_water_tracking`
  - `list_schedules`
  - `debug_water_usage`
  - `refresh_and_log_data`

- Current integration emphasis: Aiden cloud telemetry plus profile/schedule management.
- Current integration gap direction from mobile evidence: richer device patching, explicit brew control, onboarding/provisioning, notifications, and firmware/update workflows.
