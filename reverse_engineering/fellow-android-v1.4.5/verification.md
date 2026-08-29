# Verification

## Reproducibility

- Source XAPK hash captured: `012aff125d2045509411b4959fe9ab2651a099b9b88eed6eb233cbbe6cc02698`
- Hermes bundle identified as: `Hermes JavaScript bytecode, version 96`
- Static extraction is scripted via `uv run python reverse_engineering/fellow-android-v1.4.5/scripts/generate_workspace.py`
- Runtime sanitization is scripted via `uv run reverse_engineering/fellow-android-v1.4.5/scripts/sanitize_mitm_capture.py`

## Static Coverage

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
- Live device inventory/detail fields: `57` / `64`
- Highest-value unexposed telemetry and privacy differences are recorded in `evidence/runtime_telemetry_delta.md`.

## Runtime Status

- Dynamic pass status: `completed-authenticated`
- Distinct method/path pairs: `19`
- Authenticated method/path pairs: `18`
- Sanitized exchange variants: `38`
- Observed statuses: `200`, `201`, `202`, `304`, `400`, `401`
- Runtime mutations confirmed: profile create/update/delete; schedule create/update/toggle/delete; instant brew start.
- Negative runtime evidence: stop rejected during active telemetry; generic `doCancel` device patch rejected validation.
- Raw traffic scope: Fellow production API host only under ignored `generated/` during capture.
- Curated runtime output contains schemas only; scalar values, query values, and dynamic identifiers are omitted.

## Validation Checklist

- `jq empty runtime/sanitized_api_capture.json`
- Sanitizer lint and format checks with Ruff
- Curated-artifact privacy scan for bearer tokens, credentials, email values, raw device IDs, and network identifiers
- Generator rerun check confirming authenticated runtime reports are preserved when the sanitized artifact exists
- Final raw-capture flush followed by deletion of the mitmproxy flow and authenticated emulator

## Catalog Quality

- `cloud_api_catalog.yaml` records static-confirmed routes and verbs with evidence references.
- `local_protocol_map.yaml` records stable local-protocol fields and evidence references.
- `runtime/sanitized_api_capture.json` records authenticated runtime field/type evidence without secret values.
- `scripts/sanitize_mitm_capture.py` deterministically converts the ignored mitmproxy flow into the curated artifact.
- Unresolved maintenance, firmware-installation, provisioning, and destructive routes remain marked static-only instead of being invented.
