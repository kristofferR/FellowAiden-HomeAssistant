# Fellow Android 1.4.5 Reverse-Engineering Workspace

This is a reproducible static capture of `Fellow_1.4.5_APKPure.xapk` (`012aff125d2045509411b4959fe9ab2651a099b9b88eed6eb233cbbe6cc02698`). It does not modify the Home Assistant integration.

Regenerate from the default Downloads location:

```sh
uv run python reverse_engineering/fellow-android-v1.4.5/scripts/generate_workspace.py
```

Set `FELLOW_XAPK` to use another path. Heavy decompiler outputs are written under ignored `generated/`; curated evidence, catalogs, hashes, and comparisons are committed.

Start with `evidence/capture_summary.md` and `cloud_api_catalog.yaml`. Routes and verbs marked `static-confirmed` were recovered from Hermes bytecode. Runtime payload semantics that could not be established are explicitly identified as unresolved.
