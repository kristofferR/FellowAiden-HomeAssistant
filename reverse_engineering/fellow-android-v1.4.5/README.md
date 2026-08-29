# Fellow Android 1.4.5 Reverse-Engineering Workspace

This workspace contains a reproducible static capture of `Fellow_1.4.5_APKPure.xapk` (`012aff125d2045509411b4959fe9ab2651a099b9b88eed6eb233cbbe6cc02698`) plus a sanitized authenticated runtime capture. It does not modify the Home Assistant integration.

Regenerate from the default Downloads location:

```sh
uv run python reverse_engineering/fellow-android-v1.4.5/scripts/generate_workspace.py
```

Set `FELLOW_XAPK` to use another path. Heavy decompiler outputs are written under ignored `generated/`; curated evidence, catalogs, hashes, and comparisons are committed.

Start with `evidence/capture_summary.md`, `runtime/dynamic_pass.md`, and `evidence/runtime_telemetry_delta.md`. Routes and verbs marked `static-confirmed` in `cloud_api_catalog.yaml` were recovered from Hermes bytecode. The runtime reports distinguish live app traffic, direct authenticated v2 probes, negative server behavior, and intentionally untested routes.

The curated runtime artifact is `runtime/sanitized_api_capture.json`. It contains methods, normalized paths, status codes, field names, and value-free type schemas for 19 method/path pairs. Raw mitmproxy traffic is deliberately ignored under `generated/`, deleted after sanitization, and is not part of the workspace.

Regenerate the sanitized artifact from a local raw capture:

```sh
uv run reverse_engineering/fellow-android-v1.4.5/scripts/sanitize_mitm_capture.py
```
