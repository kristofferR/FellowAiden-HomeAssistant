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
- The 1.4.2 workspace did not preserve an exact route catalog, so this capture does not label individual routes as newly introduced.

## Confirmed Gaps in the Current Home Assistant Client

| Area | App 1.4.5 | Current client |
| --- | --- | --- |
| API stage | `/v2` | `/v1` |
| Refresh | `POST /auth/refresh-token` | `POST /auth/refresh` |
| Login body | `email`, `password`, `timezone` | `email`, `password` |
| Public profile | `GET /shared/{dropType}/{profileId}` | `GET /shared/{bid}` |
| Profile mutations | Client adds `settingsVersion` | No `settingsVersion` handling |
| Brew/maintenance | Start, stop, clean, and rinse routes are present | No direct actions |

The exact route inventory is in `cloud_api_catalog.yaml`. No integration code was changed during this capture.

## Next Runtime Capture

1. Record authenticated login, refresh, and device-list exchanges against API v2.
2. Record profile create/update/delete conflicts to establish `settingsVersion` semantics.
3. Record schedule responses and generic device patch payloads.
4. With the brewer in a safe state, record start/stop/clean/rinse requests and responses.

`adb` and an Android target were unavailable on this host, so those runtime checks remain deferred.
