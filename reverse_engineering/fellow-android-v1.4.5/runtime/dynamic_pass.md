# Dynamic Pass

## Result

- Status: `completed-authenticated`
- Capture date: `2026-08-29`
- App: Fellow Android `1.4.5` (`versionCode` `52`)
- API: `https://l8qtmnc692.execute-api.us-west-2.amazonaws.com/v2`
- Curated artifact: `sanitized_api_capture.json`

The original signed production split APKs ran in an Android 11 Google APIs x86 emulator with built-in ARMv7 translation. Frida `17.17.0` supplied process-local Java TLS trust hooks, and mitmproxy `12.2.3` intercepted only the Fellow API gateway. App code and resources were not rebuilt.

The pass combined app-driven interactions with direct v2 requests using the authenticated session. Direct requests covered live telemetry polling, token refresh/login fallback, profile detail, instant brew start, stop behavior, and server validation of a rejected generic device patch.

## Captured Exchanges

| Method | Path | Status | Notes |
| --- | --- | ---: | --- |
| `POST` | `/v2/auth/login` | `201` | Request fields are `email`, `password`, and `timezone`; response contains both tokens. |
| `POST` | `/v2/auth/refresh-token` | `201`, `401` | Request contains `refreshToken`; successful responses returned `accessToken` without rotating the refresh token. A fresh login recovered after the original refresh token later expired. |
| `GET` | `/v2/users/profile` | `200`, `304` | Bearer-authenticated user fetch with conditional caching. |
| `GET` | `/v2/devices?dataType=real` | `200`, `304` | Live device inventory with 57 observed fields. |
| `GET` | `/v2/devices/{id}?dataType=real` | `200`, `401` | Device detail with 64 observed fields, embedded profiles/schedules, live phase state, and nullable telemetry. |
| `PATCH` | `/v2/devices/{id}` | `400` | A direct `doCancel` patch was rejected as an unknown property and made no state change. |
| `GET` | `/v2/devices/{id}/profiles` | `200`, `401` | Profile collection with nullable fields and integer/fractional numeric variants. |
| `GET` | `/v2/devices/{id}/profiles/{id}` | `200` | Direct read of a built-in profile. |
| `POST` | `/v2/devices/{id}/profiles` | `201`, `401` | Full hot-profile body. The 401 triggered refresh and retry. |
| `PATCH` | `/v2/devices/{id}/profiles/{id}` | `200` | Five distinct request schemas covered rename, all visible hot parameters, cold mode/duration, and bloom enable/disable. |
| `DELETE` | `/v2/devices/{id}/profiles/{id}` | `202`, `401` | Three successful deletions, including the temporary capture profile. |
| `GET` | `/v2/devices/{id}/schedules` | `200`, `304`, `401` | Empty before and after a complete temporary schedule lifecycle. |
| `POST` | `/v2/devices/{id}/schedules` | `201` | Body fields are `amountOfWater`, `days`, `enabled`, `profileId`, and `secondFromStartOfTheDay`. |
| `PATCH` | `/v2/devices/{id}/schedules/{id}` | `200` | One full edit and one `enabled`-only toggle. |
| `DELETE` | `/v2/devices/{id}/schedules/{id}` | `202` | Temporary schedule removed after first disabling it. |
| `PATCH` | `/v2/devices/{id}/start?confirm=true` | `200` | No request body for instant brew; response was the selected profile plus the water amount. |
| `PATCH` | `/v2/devices/{id}/stop` | `400` | Four attempts returned “Brew is not in progress” while device telemetry was advancing through brew phases. |
| `GET` | `/v2/devices/{id}/updates` | `200` | Response fields include `deviceId`, `firmwareVersion`, and `isUpdateAvailable`. |
| `POST` | `/v2/firebase/notifications` | `201` | Automatic FCM registration. |

The curated file contains 19 distinct method/path pairs and 38 value-free exchange variants before final capture flush. Counts are rechecked during verification.

## Profile Coverage

The temporary profile exercised every visible edit control in both hot and cold modes: title, overall temperature, ratio, bloom toggle/ratio/time/temperature, single-serve pulse count/interval/temperatures, batch pulse count/interval/temperatures, cold-brew toggle, and cold duration. Fractional ratios and pulse temperatures produced separate numeric schemas. The request bodies observed at runtime did not include `settingsVersion`, despite the static helper suggesting that it can be client-added.

Two user-selected custom profiles and the temporary profile were deleted. The preserved profiles requested by the user were not modified. The temporary profile no longer exists.

## Schedule Coverage

A temporary schedule was created, then its profile, water amount, ready time, and repeat days were changed. It was saved, toggled off from the schedule list, and deleted. The schedule collection returned to empty, so it cannot run later.

## Brew and Notification Observations

During a physical-panel brew, direct API polling observed live basket, lid, water, brew-state, heater, and pump fields. Android logcat recorded repeated `RNFirebaseMsgReceiver` deliveries, including messages around phase changes and completion. No active visible Fellow notification appeared in Android's notification service while the app was foregrounded, consistent with data-only/background refresh messages.

The direct instant-start request returned 200 and the brewer moved through state codes `b`, `p1`, `p3`, and `d`, then returned to `brewing: false`, `state: null`, `heaterOn: false`, and `pumpOn: false`. The stop endpoint's 400 response during those phases is a server/API inconsistency worth preserving as negative evidence.

## Safety Boundary

The pass created and removed only temporary profile/schedule data, plus the two explicit profile deletions requested by the user. It did not share profiles, clean, rinse, provision, factory-reset, delete, or update firmware on the brewer. The short API-started brew completed and left the brewer idle.

## Privacy Handling

The sanitizer records field names and JSON types only. It removes every scalar value, normalizes dynamic path identifiers, omits query values, and records only whether bearer authentication was present. The raw mitmproxy capture contains credentials and tokens under ignored `generated/` and is deleted after the final sanitizer run.

## Remaining Runtime Gaps

- Cleaning and rinsing transitions remain untested.
- Firmware installation, provisioning, factory reset, device deletion, sharing, and public/drop profile routes remain intentionally untested.
- A positive firmware-upgrade case and non-null `brewingWaterTemperatureC`, `awsStatus`, and `firmwareCommittish` values were not available.
- `/stop` needs another hardware/app version comparison because the v2 service rejected it while telemetry showed an active API-started brew.
