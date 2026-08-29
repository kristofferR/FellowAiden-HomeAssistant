# Fellow Android 1.4.5 Capture Summary

## Artifact

- Package: `com.fellowproducts.Fellow`
- Version: `1.4.5` (`versionCode` `52`)
- Source: `Fellow_1.4.5_APKPure.xapk`
- SHA-256: `012aff125d2045509411b4959fe9ab2651a099b9b88eed6eb233cbbe6cc02698`
- Hermes bytecode: version 96

## Comparison with the Stored 1.4.2 Capture

- The production API gateway remains `https://l8qtmnc692.execute-api.us-west-2.amazonaws.com/v2`.
- The copied `BuildConfig` differs only in DEX origin plus app version (`1.4.2`/47 to `1.4.5`/52).
- The Android wrapper adds Firebase Crashlytics/session components. Core package, deep links, and gateway are unchanged.
- The 1.4.2 workspace did not preserve an exact route catalog or authenticated response schemas, so individual telemetry fields cannot be reliably labeled as newly introduced.

## Confirmed Gaps in the Current Home Assistant Client

| Area | App/API 1.4.5 runtime | Current client |
| --- | --- | --- |
| API stage | `/v2` | `/v1` |
| Refresh | `POST /auth/refresh-token`, success `201` | `POST /auth/refresh`, expects only `200` |
| Login body | `email`, `password`, `timezone`, success `201` | `email`, `password` |
| Public profile | Static route `/shared/{dropType}/{profileId}` | `/shared/{bid}` |
| Profile mutations | Runtime create/update/delete bodies did not contain `settingsVersion` | No `settingsVersion` handling |
| Schedule mutations | Runtime-confirmed full create/update, enabled-only patch, and delete | Implemented against v1 |
| Brew control | Instant start returned 200; stop returned 400 during active telemetry | No direct actions |
| Telemetry | 57 inventory fields and 64 detail fields | Core counters/state only |

The exact static route inventory is in `cloud_api_catalog.yaml`. No Home Assistant integration behavior was changed during this capture.

## Authenticated Runtime Confirmation

The dynamic pass confirmed login, token refresh, user profile, device inventory/detail, profiles, schedules, firmware-update checks, Firebase registration, profile and schedule lifecycles, direct profile detail, and instant brew start. The sanitizer records 19 distinct method/path pairs and 38 value-free exchange variants.

Profile edits covered every visible hot and cold setting. Schedule edits covered profile, water amount, time, repeat days, and enabled state. All temporary objects were removed. Two additional custom-profile deletions were explicitly selected by the user.

The direct telemetry pass observed `state` phase transitions plus `pumpOn`, `heaterOn`, basket, shower-head, lid, water, connectivity, capability flags, sync state, and firmware-update state. The server advertised `remoteBrewing` in `enabledFlags`. See `runtime_telemetry_delta.md` for the HA exposure and privacy analysis.

The Series 1 project's [protocol notes](https://github.com/hazy-dreams/Fellow-Espresso-Series1-HomeAssistant/blob/main/PROTOCOL.md) corroborate the shared v2/auth/discovery model and diagnostics privacy concerns, while its `/solo` profile and device shapes remain product-specific.

See `runtime/dynamic_pass.md` for the lifecycle details and safety boundary. `runtime/sanitized_api_capture.json` is the complete scalar-free runtime artifact.
