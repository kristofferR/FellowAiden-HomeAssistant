# Verification

## Reproducibility

- Source XAPK hash captured: `012aff125d2045509411b4959fe9ab2651a099b9b88eed6eb233cbbe6cc02698`
- Hermes bundle identified as: `Hermes JavaScript bytecode, version 96`
- Static extraction is scripted via `uv run python reverse_engineering/fellow-android-v1.4.5/scripts/generate_workspace.py`

## Coverage

| Feature | Status | Evidence Hits |
| --- | --- | ---: |
| `auth` | `covered` | `16` |
| `device_list` | `covered` | `287` |
| `claim_provision` | `covered` | `17` |
| `wifi` | `covered` | `26` |
| `profiles` | `covered` | `43` |
| `schedules` | `covered` | `22` |
| `brew_control` | `covered` | `48` |
| `notifications` | `covered` | `12` |
| `firmware_update` | `covered` | `5` |

## Integration Cross-Check

- Current HA service count: `11`
- Services discovered: `create_profile, delete_profile, create_schedule, delete_schedule, toggle_schedule, list_profiles, get_profile_details, reset_water_tracking, list_schedules, debug_water_usage, refresh_and_log_data`

## Runtime Status

- Dynamic pass status: `blocked`
- Reason: `adb is not installed on this host.`

## Catalog Quality

- `cloud_api_catalog.yaml` records static-confirmed routes and verbs with evidence references.
- `local_protocol_map.yaml` generated with stable fields and evidence references.
- Unresolved calibration routes and payload semantics remain explicitly marked instead of being invented.
