# Dynamic Pass Status

## Local Runtime Check
- `adb` present: `false`
- `emulator` present: `false`
- Attached Android targets:
```text
adb unavailable
```

## Result

- Dynamic pass is blocked locally: `adb` is not installed on this host.

## Deferred Checklist

1. Install Android platform tools or use the existing Windows capture host.
2. Attach a rooted/debuggable Android device or a compatible ARM-capable emulator.
3. Install the split APK set from `generated/apks/`.
4. Capture authenticated app traffic and reconcile it with `cloud_api_catalog.yaml`.
