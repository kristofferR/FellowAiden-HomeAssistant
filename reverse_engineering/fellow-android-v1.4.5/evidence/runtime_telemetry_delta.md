# Runtime Telemetry Delta

## Sources

- Authenticated Aiden v2 schemas in `runtime/sanitized_api_capture.json`.
- Current entity and diagnostics usage in `custom_components/fellow/`.
- The Series 1 project's [sanitized protocol notes](https://github.com/hazy-dreams/Fellow-Espresso-Series1-HomeAssistant/blob/main/PROTOCOL.md), used only as a cross-product comparison.

The live Aiden device collection exposed 57 fields. The device-detail response exposed 64 fields. The schemas are value-free, but selected non-sensitive values were checked directly while the brewer moved through idle and brew phases.

## Highest-Value Home Assistant Deltas

| API field | Runtime behavior | Current HA use | Recommendation |
| --- | --- | --- | --- |
| `state` | `null` while idle and an object during brewing. Its `value` moved through `b`, `p1`, `p3`, and `d` before returning to `null`. The object also repeated basket, carafe, lid, water, shower-head, and error state. | Not used. | Prefer a translated brew-phase sensor or use it to validate the existing `brewing` binary sensor. Keep the raw object out of entity state. |
| `pumpOn` | Toggled during the API-started brew and returned to `false` at completion. | Not exposed. | Add a disabled-by-default diagnostic binary sensor. |
| `showerHeadPresent` | Boolean and changed independently from basket/carafe presence. | Not exposed. | Add a problem or presence binary sensor after confirming the desired HA polarity. |
| `cleaning`, `rinsing` | Stable booleans while idle. | Not exposed. | Add disabled-by-default running binary sensors. Capture real maintenance transitions before enabling them by default. |
| `isConnected`, `connectionTimestamp` | `isConnected` was true while online; the timestamp was a millisecond epoch string. | Coordinator availability only reflects HTTP poll success. | Add device-cloud connectivity diagnostics or incorporate `isConnected` into entity availability with a conservative grace period. |
| `firmwareUpgradeRequired` | Boolean; false during this pass. | Firmware version is device metadata, but upgrade state is not exposed. | Add an update/problem entity only after a positive update case is captured. |
| `brewingProfileId` | Nullable string in the runtime schema. | Current-profile logic infers from `ibSelectedProfileId`, last-used time, or a default profile. | Prefer `brewingProfileId` while non-null, without exposing the ID itself. |
| `ibWaterQuantity` | Integer representing the configured instant-brew water amount. | Not exposed. | Useful as a target-volume number or diagnostic sensor if remote brew is implemented. |
| `enabledFlags` | Advertised `base`, `profiles`, `notifications`, `schedules`, and `remoteBrewing` during this pass. | Not used. | Gate optional features and actions from server capability flags instead of assuming availability. |
| `unsynced` | Array, empty after the completed test lifecycle. | Not exposed. | Treat non-empty state as a diagnostic sync problem after its item schema is observed. |
| `brewingWaterTemperatureC` | Present but always `null`, including the observed brew. | Not exposed. | Do not add an entity yet. The field needs a non-null hardware trace first. |
| `awsStatus`, `firmwareCommittish` | Present but always `null`. | Not exposed. | Keep out of HA until behavior is proven. |

The existing integration already consumes the core counters, last-brew volume/timestamps, `brewing`, carafe, heater, lid, missing-water, basket fields, selected profile, firmware version, elevation, and network/Bluetooth MAC addresses.

## Brew-State Finding

The physical-panel brew produced repeated cloud updates and Firebase receiver events. After the machine had physically finished, `brewing` remained true in direct v2 reads until the later API-started brew completed. During the API-started brew, `state`, `heaterOn`, and `pumpOn` tracked the phase changes more precisely. This makes `brewing` alone unsafe as a high-frequency source of truth without an idle/state cross-check.

## Diagnostics Privacy Gap

The v2 detail response includes `publicIpAddress`, `localIpAddress`, `wifiSsid`, `serialNumber`, `wifiMacAddress`, and `btMacAddress`. Current diagnostics redact `localIpAddress` and both MAC fields, but the SSID key is cased as `wifiSSID` while the live API uses `wifiSsid`; `publicIpAddress` and `serialNumber` are also not redacted. These should be fixed before broadening telemetry exposure. Device IDs and user-provided display names should remain private diagnostics data as recommended by the Series 1 protocol notes.

## Series 1 Comparison

The Series 1 notes independently corroborate the v2 gateway, `/auth/refresh-token`, `dataType=real`, typed device prefixes, and the need to preserve multiple-device selection. Its `/v2/solo/...` profile and telemetry shapes are product-specific and should not be applied to Aiden entities. The shared discovery/privacy guidance is reusable; the Solo BLE/profile recipe model is not.
