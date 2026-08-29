# Fellow API v2 integration notes

These notes describe the small, generalized API surface used by this Home
Assistant integration. They intentionally exclude application source,
captures, account data, device identifiers, tokens, and copied payloads.

The API is an undocumented mobile interface and can change without notice.
Authenticated operations use bearer authentication and are scoped to a
selected Aiden brewer. Login exchanges account credentials for those tokens.

## Authentication and inventory

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/auth/login` | Exchange account credentials for access and refresh tokens. |
| `POST` | `/auth/refresh-token` | Refresh an expired access token. |
| `GET` | `/devices?dataType=real` | List account devices and live inventory. |
| `GET` | `/devices/{deviceId}?dataType=real` | Refresh one selected brewer. |

The integration probes profile and schedule routes before accepting a device.
This keeps other Fellow product types out of the Aiden integration without
depending on a display name or a brittle model-name list.

## Profiles and schedules

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`, `POST` | `/devices/{deviceId}/profiles` | List or create profiles. |
| `GET`, `PATCH`, `DELETE` | `/devices/{deviceId}/profiles/{profileId}` | Read, update, or delete a profile. |
| `GET`, `POST` | `/devices/{deviceId}/schedules` | List or create schedules. |
| `PATCH`, `DELETE` | `/devices/{deviceId}/schedules/{scheduleId}` | Toggle or delete a schedule. |

Profile writes omit server-owned identifiers and timestamps. Resource caches
are invalidated after mutation and refreshed independently of fast device
telemetry.

The mobile client also contains a selected-profile route, but an authenticated
live Aiden request is rejected by Fellow's API gateway. Home Assistant does
not expose that route as a control.

## Live telemetry

The v2 device response adds state that was absent or unreliable in the older
API, including brew phase, pump, heater, carafe, lid, shower head, water,
cleaning, rinsing, cloud connectivity, firmware-update status, and queued
changes. Home Assistant keeps stable entity semantics when a field is absent
and treats the live nested state as authoritative while a brew is active.

`brewStartTime` and `brewEndTime` advance independently while idle and must not
be subtracted without observing a matching cycle. Home Assistant records a
duration only when it sees the brewer transition from active to complete with
one corresponding counter increment.

## Cloud notifications

The mobile flow registers an Android FCM token with
`POST /firebase/notifications`. The integration receives data-only messages,
uses them as invalidation signals, and immediately refreshes each configured
brewer on the account. A polling fallback remains active because notifications
do not contain authoritative device state and the mobile protocol is not a
public contract.
