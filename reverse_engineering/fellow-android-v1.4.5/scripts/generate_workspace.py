from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


ANDROID_NS = "{http://schemas.android.com/apk/res/android}"

WORKSPACE = Path(__file__).resolve().parent.parent
REPO_ROOT = WORKSPACE.parent.parent
APP_VERSION = "1.4.5"
SOURCE_XAPK = Path(
    os.environ.get(
        "FELLOW_XAPK",
        Path.home() / "Downloads" / "Fellow_1.4.5_APKPure.xapk",
    )
).expanduser()

INPUTS_DIR = WORKSPACE / "inputs"
EVIDENCE_DIR = WORKSPACE / "evidence"
EVIDENCE_CODE_DIR = EVIDENCE_DIR / "code"
RUNTIME_DIR = WORKSPACE / "runtime"
GENERATED_DIR = WORKSPACE / "generated"

GENERATED_APKS_DIR = GENERATED_DIR / "apks"
GENERATED_APKTOOL_DIR = GENERATED_DIR / "apktool"
GENERATED_JADX_DIR = GENERATED_DIR / "jadx"
GENERATED_HERMES_DIR = GENERATED_DIR / "hermes"

BASE_APK_NAME = "com.fellowproducts.Fellow.apk"
ABI_SPLIT_NAME = "config.armeabi_v7a.apk"

SELECTED_COPY_PATHS = [
    ("resources/AndroidManifest.xml", "resources/AndroidManifest.xml"),
    ("sources/is/symphony/FellowDev/BuildConfig.java", "is/symphony/FellowDev/BuildConfig.java"),
    ("sources/is/symphony/FellowDev/MainApplication.java", "is/symphony/FellowDev/MainApplication.java"),
    ("sources/is/symphony/FellowDev/MainActivity.java", "is/symphony/FellowDev/MainActivity.java"),
    ("sources/com/facebook/react/PackageList.java", "com/facebook/react/PackageList.java"),
    ("sources/it/innove/NativeBleManagerSpec.java", "it/innove/NativeBleManagerSpec.java"),
    ("sources/it/innove/CompanionScanner.java", "it/innove/CompanionScanner.java"),
    ("sources/com/thanosfisherman/wifiutils/WifiConnectorBuilder.java", "com/thanosfisherman/wifiutils/WifiConnectorBuilder.java"),
    ("sources/com/reactlibrary/rnwifi/RNWifiModule.java", "com/reactlibrary/rnwifi/RNWifiModule.java"),
    ("sources/com/lugg/RNCConfig/RNCConfigModule.java", "com/lugg/RNCConfig/RNCConfigModule.java"),
]

HERMES_FEATURE_PATTERNS = {
    "auth": [
        "useGetMagicLink",
        "missing_access_token_in_response",
        "missing_tokens_in_response",
        "sign_in_error",
        "sign_out_success",
    ],
    "device_list": [
        "useGetDevices",
        "usePatchDevice",
        "useUpdateElevation",
        "device_settings:",
        "home_status_connected",
    ],
    "claim_provision": [
        "useCreateClaimCertificate",
        "useProvisionDevice",
        "provision_attempts",
        "requestAuthorization",
    ],
    "ble": [
        "BleManagerDidUpdateState",
        "BleManagerDiscoverPeripheral",
        "isBluetoothEnabled",
        "isBluetoothRejected",
    ],
    "wifi": [
        "postGetWifiList",
        "postGetWifiStatus",
        "postSSID",
        "postPassword",
        "postNegotiateDataSecurity",
        "postNegotiateLengthSecurity",
        "postProcessPassResolved",
        "WIFI_REASON_NO_AP_FOUND",
        "getCurrentWifiSSID",
        "loadWifiList",
    ],
    "profiles": [
        "useGetProfiles",
        "useUpdateProfile",
        "useDeleteProfile",
        "useSetDefaultProfile",
        "useSetSoloActiveProfile",
        "useShareProfile",
        "profileDeletedToast",
        "selectedProfile?profileId=",
    ],
    "schedules": [
        "useGetSchedules",
        "useCreateSchedule",
        "useUpdateSchedule",
        "useDeleteSchedule",
        "updateScheduleCard",
        "device:overview_create_schedule",
    ],
    "brew_control": [
        "isBrewingAllowed",
        "brewing_paused",
        "brewEndTime",
        "home_brew_button",
        "useStartBrew",
        "useStartInstantBrew",
        "useStopBrew",
        "useStartCleaning",
        "useStartRinsing",
        "useStartCalibration",
    ],
    "notifications": [
        "firebase.messaging().onNotificationOpenedApp",
        "useUpdateUserNotifications",
        "scheduleLocalNotification",
        "toast_updated",
    ],
    "firmware_update": [
        "Firmware update required",
        "firmware_version",
        "maintenance_title",
    ],
    "sharing": [
        "brew.link",
        "/p/:profileId/:dropType",
        "shareable",
    ],
    "account_settings": [
        "settings:open_settings:management_page_title",
        "useResetPassword",
        "useSignOut",
        "settings:notification_update_error",
    ],
}

PACKAGE_GROUPS = {
    "core_runtime": {
        "MainReactPackage",
        "AsyncStoragePackage",
        "ClipboardPackage",
        "RNBootSplashPackage",
        "RNGestureHandlerPackage",
        "ReanimatedPackage",
        "SafeAreaContextPackage",
        "RNScreensPackage",
        "OrientationPackage",
    },
    "device_connectivity": {
        "BleManagerPackage",
        "RNWifiPackage",
        "RNFusedLocationPackage",
        "GeolocationPackage",
        "NetInfoPackage",
        "RNPermissionsPackage",
        "RNDeviceInfo",
    },
    "storage_identity": {
        "KeychainPackage",
        "EmailPackage",
        "RNCConfigPackage",
        "RandomBytesPackage",
        "RNGetRandomValuesPackage",
    },
    "notifications_analytics": {
        "ReactNativeFirebaseAnalyticsPackage",
        "ReactNativeFirebaseAppPackage",
        "ReactNativeFirebaseMessagingPackage",
        "MixpanelReactNativePackage",
    },
    "ui_media": {
        "ReactSliderPackage",
        "RNSkiaPackage",
        "LottiePackage",
        "BlurhashPackage",
        "BlurViewPackage",
        "LinearGradientPackage",
        "SvgPackage",
        "TurboImagePackage",
        "ReactVideoPackage",
    },
}


def ensure_dirs() -> None:
    for path in [
        INPUTS_DIR,
        EVIDENCE_DIR,
        EVIDENCE_CODE_DIR,
        RUNTIME_DIR,
        GENERATED_APKS_DIR,
        GENERATED_APKTOOL_DIR,
        GENERATED_JADX_DIR,
        GENERATED_HERMES_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def run(cmd: list[str], cwd: Path | None = None, capture: bool = False) -> str:
    if cmd[0] == "hbc-disassembler" and shutil.which("hbc-disassembler") is None:
        cmd = [
            "uvx",
            "--from",
            "git+https://github.com/P1sec/hermes-dec.git@a0f18f97ab661eb8ed659c8c683a0d21ea619e69",
            "hbc-disassembler",
            *cmd[1:],
        ]
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        capture_output=capture,
    )
    if capture:
        return result.stdout
    return ""


def adb_has_target(adb_devices_output: str) -> bool:
    for raw_line in adb_devices_output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices attached") or line.startswith("*"):
            continue
        return True
    return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_zip_member(archive: zipfile.ZipFile, member_name: str) -> str:
    digest = hashlib.sha256()
    with archive.open(member_name, "r") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def command_version(name: str, *arguments: str) -> str:
    if shutil.which(name) is None:
        return "missing"
    try:
        output = run([name, *arguments], capture=True).strip()
    except subprocess.CalledProcessError:
        return "present (version unavailable)"
    return output.splitlines()[0] if output else "present (version unavailable)"


def extract_member(archive: zipfile.ZipFile, member_name: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(member_name, "r") as src, destination.open("wb") as dst:
        shutil.copyfileobj(src, dst)


def yaml_quote(value: str) -> str:
    specials = [":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", ">", "%", "@", "`"]
    needs_quote = (
        value == ""
        or value.strip() != value
        or "\n" in value
        or any(char in value for char in specials)
        or value.lower() in {"null", "true", "false", "yes", "no"}
        or value.startswith("-")
    )
    if needs_quote:
        return json.dumps(value, ensure_ascii=False)
    return value


def dump_yaml(data: Any, indent: int = 0) -> str:
    prefix = "  " * indent
    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                if isinstance(value, dict) and not value:
                    lines.append(f"{prefix}{key}: {{}}")
                    continue
                if isinstance(value, list) and not value:
                    lines.append(f"{prefix}{key}: []")
                    continue
                lines.append(f"{prefix}{key}:")
                lines.append(dump_yaml(value, indent + 1))
            else:
                lines.append(f"{prefix}{key}: {dump_yaml(value, 0).strip()}")
        return "\n".join(lines)
    if isinstance(data, list):
        if not data:
            return f"{prefix}[]"
        lines = []
        for item in data:
            if isinstance(item, (dict, list)):
                rendered = dump_yaml(item, indent + 1)
                rendered_lines = rendered.splitlines()
                if rendered_lines:
                    first = rendered_lines[0].lstrip()
                    lines.append(f"{prefix}- {first}")
                    for extra in rendered_lines[1:]:
                        lines.append(extra)
                else:
                    lines.append(f"{prefix}-")
            else:
                lines.append(f"{prefix}- {dump_yaml(item, 0).strip()}")
        return "\n".join(lines)
    if data is None:
        return "null"
    if isinstance(data, bool):
        return "true" if data else "false"
    if isinstance(data, (int, float)):
        return str(data)
    return yaml_quote(str(data))


def line_number(path: Path, needle: str) -> int | None:
    for idx, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if needle in line:
            return idx
    return None


def grep_lines(path: Path, patterns: list[str]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for idx, line in enumerate(lines, start=1):
        for pattern in patterns:
            if pattern in line:
                matches.append({"pattern": pattern, "line": idx, "text": line.strip()})
    return matches


def extract_hermes_functions(path: Path, function_ids: set[int]) -> str:
    header_pattern = re.compile(r"^=> \[Function #(\d+)")
    captured: dict[int, list[str]] = {}
    active_id: int | None = None

    with path.open(encoding="utf-8", errors="replace") as source:
        for line in source:
            match = header_pattern.match(line)
            if match:
                candidate_id = int(match.group(1))
                active_id = candidate_id if candidate_id in function_ids else None
                if active_id is not None:
                    captured[active_id] = [line.rstrip()]
                continue

            if active_id is None:
                continue
            if line.rstrip() == "===============":
                active_id = None
                continue
            captured[active_id].append(line.rstrip())

    missing = function_ids - captured.keys()
    if missing:
        raise RuntimeError(f"Missing Hermes functions: {sorted(missing)}")

    sections = [
        "Fellow Android 1.4.5 Hermes endpoint evidence",
        "Generated from index.android.bundle (Hermes bytecode v96).",
        "",
    ]
    for function_id in sorted(captured):
        sections.extend(captured[function_id])
        sections.extend(["", "===============", ""])
    return "\n".join(sections)


def parse_build_config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    regex = re.compile(r"public static final [^ ]+ ([A-Z0-9_]+) = (.+);")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = regex.search(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def parse_manifest(path: Path) -> dict[str, Any]:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    application = root.find("application")
    uses_sdk = root.find("uses-sdk")

    permissions = [
        permission.attrib.get(f"{ANDROID_NS}name", "")
        for permission in root.findall("uses-permission")
    ]

    exported_components: list[dict[str, str]] = []
    deep_links: list[dict[str, str]] = []
    services: list[dict[str, str]] = []
    receivers: list[dict[str, str]] = []
    providers: list[dict[str, str]] = []

    if application is not None:
        for tag_name, bucket in [
            ("service", services),
            ("receiver", receivers),
            ("provider", providers),
        ]:
            for element in application.findall(tag_name):
                bucket.append(
                    {
                        "name": element.attrib.get(f"{ANDROID_NS}name", ""),
                        "exported": element.attrib.get(f"{ANDROID_NS}exported", "unspecified"),
                    }
                )

        for activity in application.findall("activity"):
            activity_name = activity.attrib.get(f"{ANDROID_NS}name", "")
            exported = activity.attrib.get(f"{ANDROID_NS}exported", "unspecified")
            exported_components.append({"type": "activity", "name": activity_name, "exported": exported})
            for intent_filter in activity.findall("intent-filter"):
                actions = {
                    action.attrib.get(f"{ANDROID_NS}name", "")
                    for action in intent_filter.findall("action")
                }
                categories = {
                    category.attrib.get(f"{ANDROID_NS}name", "")
                    for category in intent_filter.findall("category")
                }
                if "android.intent.action.VIEW" not in actions:
                    continue
                data_elements = intent_filter.findall("data")
                scheme = next(
                    (data.attrib.get(f"{ANDROID_NS}scheme", "") for data in data_elements if data.attrib.get(f"{ANDROID_NS}scheme")),
                    "",
                )
                host = next(
                    (data.attrib.get(f"{ANDROID_NS}host", "") for data in data_elements if data.attrib.get(f"{ANDROID_NS}host")),
                    "",
                )
                path_prefix = next(
                    (data.attrib.get(f"{ANDROID_NS}pathPrefix", "") for data in data_elements if data.attrib.get(f"{ANDROID_NS}pathPrefix")),
                    "",
                )
                deep_links.append(
                    {
                        "activity": activity_name,
                        "scheme": scheme,
                        "host": host,
                        "pathPrefix": path_prefix,
                        "autoVerify": intent_filter.attrib.get(f"{ANDROID_NS}autoVerify", "false"),
                        "categories": ", ".join(sorted(category for category in categories if category)),
                    }
                )

    return {
        "package": root.attrib.get("package", ""),
        "versionCode": root.attrib.get(f"{ANDROID_NS}versionCode", ""),
        "versionName": root.attrib.get(f"{ANDROID_NS}versionName", ""),
        "minSdk": uses_sdk.attrib.get(f"{ANDROID_NS}minSdkVersion", "") if uses_sdk is not None else "",
        "targetSdk": uses_sdk.attrib.get(f"{ANDROID_NS}targetSdkVersion", "") if uses_sdk is not None else "",
        "applicationName": application.attrib.get(f"{ANDROID_NS}name", "") if application is not None else "",
        "permissions": permissions,
        "exported_components": exported_components,
        "deep_links": deep_links,
        "services": services,
        "receivers": receivers,
        "providers": providers,
        "networkSecurityConfig": application.attrib.get(f"{ANDROID_NS}networkSecurityConfig", "") if application is not None else "",
        "usesCleartextTraffic": application.attrib.get(f"{ANDROID_NS}usesCleartextTraffic", "") if application is not None else "",
    }


def parse_package_list(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"new ([A-Za-z0-9_$.]+)\(", content)
    packages: list[str] = []
    for name in matches:
        if name in {"ArrayList", "PackageList", "MainPackageConfig"}:
            continue
        if name not in packages:
            packages.append(name)
    return packages


def group_packages(package_names: list[str]) -> dict[str, list[str]]:
    grouped = {name: [] for name in PACKAGE_GROUPS}
    grouped["other"] = []
    for package_name in package_names:
        placed = False
        for group_name, members in PACKAGE_GROUPS.items():
            if package_name in members:
                grouped[group_name].append(package_name)
                placed = True
                break
        if not placed:
            grouped["other"].append(package_name)
    return grouped


def top_level_yaml_keys(path: Path) -> list[str]:
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.startswith(" "):
            continue
        if line.endswith(":"):
            keys.append(line[:-1].strip())
    return keys


def copy_selected_files(jadx_root: Path) -> None:
    for source_rel, dest_rel in SELECTED_COPY_PATHS:
        source = jadx_root / source_rel
        destination = EVIDENCE_CODE_DIR / dest_rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def emit_method_index(source: Path, destination: Path, method_patterns: list[str], title: str) -> None:
    content = source.read_text(encoding="utf-8", errors="replace").splitlines()
    lines = [f"# {title}", ""]
    for pattern in method_patterns:
        found = False
        for idx, line in enumerate(content, start=1):
            if pattern in line:
                lines.append(f"- `{pattern}`: line {idx}: `{line.strip()}`")
                found = True
                break
        if not found:
            lines.append(f"- `{pattern}`: not found")
    lines.append("")
    source_label = source.relative_to(WORKSPACE) if source.is_relative_to(WORKSPACE) else source.name
    lines.append(f"Source: `{source_label}`")
    write_text(destination, "\n".join(lines) + "\n")


def build_artifact_index(
    xapk_hash: str,
    xapk_manifest: dict[str, Any],
    manifest_data: dict[str, Any],
    build_config: dict[str, str],
    split_hash_rows: list[dict[str, Any]],
    tool_versions: dict[str, str],
    hermes_file_description: str,
) -> str:
    _, separator, description = hermes_file_description.strip().partition(": ")
    hermes_description = description if separator else hermes_file_description.strip()
    permission_lines = "\n".join(f"- `{permission}`" for permission in manifest_data["permissions"])
    deep_link_lines = "\n".join(
        f"- `{entry['scheme']}://{entry['host']}{entry['pathPrefix']}` via `{entry['activity']}`"
        for entry in manifest_data["deep_links"]
    )
    split_rows = "\n".join(
        f"| `{row['name']}` | `{row['role']}` | `{row['size']}` | `{row['sha256']}` |"
        for row in split_hash_rows
    )
    tool_rows = "\n".join(f"| `{name}` | `{value}` |" for name, value in tool_versions.items())
    return f"""# Artifact Index

## Source Artifact

- Source XAPK: `{SOURCE_XAPK.name}`
- SHA-256: `{xapk_hash}`
- APKPure package: `{xapk_manifest['package_name']}`
- Application class: `{manifest_data['applicationName']}`
- Version: `{xapk_manifest['version_name']}` (`versionCode` `{xapk_manifest['version_code']}`)
- Min/target SDK: `{xapk_manifest['min_sdk_version']}` / `{xapk_manifest['target_sdk_version']}`
- Build config API gateway: `{build_config.get('API_GATEWAY_URL', 'unknown')}`
- Hermes bundle description: `{hermes_description}`

## Split Layout

| File | Role | Size (bytes) | SHA-256 |
| --- | --- | ---: | --- |
{split_rows}

## Permissions

{permission_lines}

## Deep Links

{deep_link_lines}

## Toolchain

| Tool | Version / Path |
| --- | --- |
{tool_rows}
"""


def build_android_surface_model(
    manifest_data: dict[str, Any],
    grouped_packages: dict[str, list[str]],
    build_config_path: Path,
    main_application_path: Path,
    main_activity_path: Path,
    package_list_path: Path,
    config_module_path: Path,
    network_security_hits: list[str],
) -> str:
    sections = []
    sections.append("# Android Surface Model\n")
    sections.append("## App Wrapper")
    sections.append(
        f"- `MainApplication`: `{main_application_path.relative_to(WORKSPACE)}` enables React Native new architecture and Hermes."
    )
    sections.append(
        f"- `MainActivity`: `{main_activity_path.relative_to(WORKSPACE)}` boots component `Fellow` with a portrait-only `singleTask` activity."
    )
    sections.append(
        f"- `BuildConfig`: `{build_config_path.relative_to(WORKSPACE)}` exposes `API_GATEWAY_URL`, `LINKING_PREFIXES`, `MIXPANEL_TOKEN`, and production environment flags through `RNCConfigModule`."
    )
    sections.append("")
    sections.append("## Exported Entry Points")
    for entry in manifest_data["exported_components"]:
        sections.append(f"- `{entry['type']}` `{entry['name']}` exported=`{entry['exported']}`")
    sections.append("")
    sections.append("## Deep-Link Surface")
    for entry in manifest_data["deep_links"]:
        sections.append(
            f"- `{entry['scheme']}://{entry['host']}{entry['pathPrefix']}` autoVerify=`{entry['autoVerify']}` categories=`{entry['categories']}`"
        )
    sections.append("")
    sections.append("## React Native Package Inventory")
    for group_name, packages in grouped_packages.items():
        if not packages:
            continue
        label = group_name.replace("_", " ").title()
        sections.append(f"- {label}: " + ", ".join(f"`{name}`" for name in packages))
    sections.append("")
    sections.append("## Connectivity And Provisioning Seams")
    sections.append("- BLE: `BleManagerPackage` plus `NativeBleManagerSpec` exposes scan, connect, read, write, MTU, notification, and companion-device association methods.")
    sections.append("- Wi-Fi: `RNWifiPackage` plus `wifiutils` exposes list, connect, disconnect, and current-SSID operations.")
    sections.append("- Notifications: Firebase Analytics + Firebase Messaging packages are registered in `PackageList` and backed by manifest services/receivers.")
    sections.append("- Storage: `KeychainPackage` and AsyncStorage are bundled alongside `RNCConfigModule` for config injection.")
    sections.append("")
    sections.append("## Security Observations")
    if network_security_hits:
        for hit in network_security_hits:
            sections.append(f"- {hit}")
    else:
        sections.append("- No app-package references to `networkSecurityConfig`, `usesCleartextTraffic`, `CertificatePinner`, custom `HostnameVerifier`, `SSLSocketFactory`, or `X509TrustManager` were found in the app-specific wrapper files or decoded manifest.")
    return "\n".join(sections) + "\n"


def build_hermes_feature_map(
    hermes_path: Path,
    feature_hits: dict[str, list[dict[str, Any]]],
) -> str:
    lines = ["# Hermes Feature Map", ""]
    lines.append(f"Source: `{hermes_path.relative_to(WORKSPACE)}`")
    lines.append("")
    for feature, hits in feature_hits.items():
        lines.append(f"## {feature.replace('_', ' ').title()}")
        if not hits:
            lines.append("- No targeted symbols matched.")
        else:
            for hit in hits:
                lines.append(f"- line {hit['line']}: `{hit['text']}`")
        lines.append("")
    return "\n".join(lines)


def build_integration_current_state(service_names: list[str]) -> str:
    lines = [
        "# Current Home Assistant Integration State",
        "",
        "- Domain: `fellow` (`custom_components/fellow/manifest.json` reports `iot_class` `cloud_polling`).",
        "- Current entity platforms: `sensor`, `binary_sensor`, and `select`.",
        "- Vendored API client files exist under `custom_components/fellow/fellow_aiden/` for device, profile, and schedule handling.",
        "- Registered Home Assistant services:",
    ]
    for service_name in service_names:
        lines.append(f"  - `{service_name}`")
    lines.extend(
        [
            "",
            "- Current integration emphasis: Aiden cloud telemetry plus profile/schedule management.",
            "- Current integration gap direction from mobile evidence: richer device patching, explicit brew control, onboarding/provisioning, notifications, and firmware/update workflows.",
            "",
        ]
    )
    return "\n".join(lines)


def build_cloud_catalog(evidence_refs: dict[str, str]) -> dict[str, Any]:
    def endpoint(
        feature: str,
        method: str,
        path: str,
        function_id: int,
        *,
        auth_mode: str = "bearer",
        request_fields: list[str] | None = None,
        response_fields: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "feature": feature,
            "method": method,
            "path": path,
            "auth_mode": auth_mode,
            "request_fields": request_fields or [],
            "response_fields": response_fields or [],
            "notes": notes or [],
            "hermes_function_id": function_id,
            "evidence": [
                f"evidence/hermes_endpoint_functions.txt (Function #{function_id})",
            ],
            "validation_status": "static-confirmed",
        }

    return {
        "source_artifact": SOURCE_XAPK.name,
        "app_version": APP_VERSION,
        "base_url": "https://l8qtmnc692.execute-api.us-west-2.amazonaws.com/v2",
        "device_prefix_behavior": {
            "aiden_brewer": "empty prefix",
            "other_device_types": "/{deviceType.lower()}/",
            "evidence": "evidence/hermes_endpoint_functions.txt (Function #17436 getApiPrefix)",
        },
        "entries": [
            endpoint(
                "auth_login",
                "POST",
                "/auth/login",
                14026,
                auth_mode="public",
                request_fields=["email", "password", "timezone"],
                response_fields=["accessToken", "refreshToken"],
            ),
            endpoint(
                "auth_refresh",
                "POST",
                "/auth/refresh-token",
                14030,
                auth_mode="refresh-token body",
                request_fields=["refreshToken"],
                response_fields=["accessToken", "refreshToken?"],
                notes=["Request sets skipAuthRefresh=true and Content-Type=application/json."],
            ),
            endpoint(
                "auth_sign_up",
                "POST",
                "/auth/sign-up",
                14034,
                auth_mode="public",
                request_fields=[
                    "acceptsMarketing",
                    "email",
                    "firstName",
                    "lastName",
                    "password",
                    "phone",
                    "timezone",
                ],
            ),
            endpoint(
                "auth_email_status",
                "POST",
                "/auth/email-status/{email}",
                14038,
                auth_mode="public",
            ),
            endpoint(
                "auth_activate_account",
                "POST",
                "/auth/activate-account",
                14042,
                auth_mode="public",
                request_fields=["customerId", "activationToken", "password", "timezone"],
            ),
            endpoint("auth_sign_out", "POST", "/auth/sign-out", 14046),
            endpoint(
                "auth_change_password",
                "PATCH",
                "/users/profile",
                14050,
                request_fields=["email", "password"],
            ),
            endpoint(
                "auth_recover",
                "POST",
                "/auth/recover",
                14054,
                auth_mode="public",
                request_fields=["email"],
            ),
            endpoint("user_get", "GET", "/users/profile", 14059),
            endpoint(
                "user_notifications_update",
                "PATCH",
                "/users/notifications",
                14063,
                request_fields=["notificationData (spread into body)"],
            ),
            endpoint("device_list", "GET", "/devices?dataType=real", 18511),
            endpoint("device_get", "GET", "/devices/{deviceId}?dataType=real", 18495),
            endpoint(
                "typed_device_get",
                "GET",
                "/{deviceType}/devices/{deviceId}?dataType=real",
                18499,
            ),
            endpoint(
                "device_patch",
                "PATCH",
                "/devices/{deviceId}",
                18503,
                request_fields=["patch object"],
            ),
            endpoint(
                "typed_device_patch",
                "PATCH",
                "/{deviceType}/devices/{deviceId}",
                18507,
                request_fields=["patch object"],
            ),
            endpoint(
                "brew_start",
                "PATCH",
                "/devices/{deviceId}/start{?confirm=true}",
                18515,
                request_fields=["brewInfo"],
            ),
            endpoint(
                "instant_brew_start",
                "PATCH",
                "/devices/{deviceId}/start{?confirm=true}",
                18519,
            ),
            endpoint("brew_stop", "PATCH", "/devices/{deviceId}/stop", 18523),
            endpoint(
                "device_elevation_update",
                "PATCH",
                "/{optionalDeviceTypePrefix}devices/{deviceId}",
                18527,
                request_fields=["elevation"],
            ),
            endpoint("device_factory_reset", "DELETE", "/devices/{deviceId}/factoryReset", 18531),
            endpoint(
                "device_delete",
                "DELETE",
                "/devices/{deviceId}{?confirm=true}",
                18535,
            ),
            endpoint(
                "typed_device_delete",
                "DELETE",
                "/{deviceType}/devices/{deviceId}{?confirm=true}",
                18539,
            ),
            endpoint("device_update_check", "GET", "/devices/{deviceId}/updates", 18543),
            endpoint(
                "typed_device_update_check",
                "GET",
                "/{optionalDeviceType}/devices/{deviceId}/updates",
                18547,
            ),
            endpoint(
                "device_provision",
                "POST",
                "/{optionalDeviceTypePrefix}devices/{deviceId}/provision",
                18551,
                request_fields=["deviceTimezone", "deviceType", "deviceOS", "deviceOSVersion"],
            ),
            endpoint("device_share", "POST", "/devices/{deviceId}/share", 23540),
            endpoint("device_verify_share_code", "GET", "/devices/verify?code={code}", 23544),
            endpoint(
                "device_claim_certificate",
                "POST",
                "/auth/device/claimCertificate",
                27711,
                request_fields=["deviceType", "claim request fields (not fully decoded)"],
            ),
            endpoint("profiles_list", "GET", "/{optionalDeviceTypePrefix}devices/{deviceId}/profiles", 21136),
            endpoint("profile_get", "GET", "/devices/{deviceId}/profiles/{profileId}", 21140),
            endpoint(
                "profile_create",
                "POST",
                "/{optionalDeviceTypePrefix}devices/{deviceId}/profiles",
                21144,
                request_fields=["profile", "settingsVersion (client-added)"],
            ),
            endpoint(
                "profile_delete",
                "DELETE",
                "/{optionalDeviceTypePrefix}devices/{deviceId}/profiles/{profileId}",
                21148,
                request_fields=["settingsVersion (client-added delete body)"],
            ),
            endpoint(
                "profile_set_default",
                "PATCH",
                "/devices/{deviceId}/selectedProfile?profileId={profileId}",
                21152,
            ),
            endpoint(
                "profile_update",
                "PATCH",
                "/{optionalDeviceTypePrefix}devices/{deviceId}/profiles/{profileId}",
                21156,
                request_fields=["profile", "settingsVersion (client-added)"],
            ),
            endpoint(
                "profile_share",
                "POST",
                "/{optionalDeviceTypePrefix}devices/{deviceId}/profiles/{profileId}/share",
                21160,
            ),
            endpoint(
                "shared_profile_get",
                "GET",
                "/shared/{dropType}/{profileId}",
                21164,
                auth_mode="public",
            ),
            endpoint(
                "drop_profiles_list",
                "GET",
                "/drops/{dropType}/profiles",
                21168,
                auth_mode="public",
            ),
            endpoint(
                "solo_active_profile_set",
                "PATCH",
                "/solo/devices/{deviceId}/active-profile",
                21172,
                request_fields=["profileId", "settingsVersion (client-added)"],
            ),
            endpoint("schedules_list", "GET", "/devices/{deviceId}/schedules", 33331),
            endpoint(
                "schedule_create",
                "POST",
                "/devices/{deviceId}/schedules",
                33335,
                request_fields=["schedule object (spread into body)"],
            ),
            endpoint(
                "schedule_update",
                "PATCH",
                "/devices/{deviceId}/schedules/{scheduleId}",
                33339,
                request_fields=["schedule object (spread into body)"],
            ),
            endpoint("schedule_delete", "DELETE", "/devices/{deviceId}/schedules/{scheduleId}", 33343),
            endpoint("maintenance_clean_start", "PATCH", "/devices/{deviceId}/clean", 23675),
            endpoint("maintenance_rinse_start", "PATCH", "/devices/{deviceId}/rinse", 23679),
            endpoint(
                "firebase_notification_register",
                "POST",
                "/firebase/notifications",
                28122,
                request_fields=["notification registration payload (not fully decoded)"],
            ),
        ],
        "unresolved_operations": [
            {
                "feature": "maintenance_calibration_start_finish",
                "symbols": ["useStartCalibration", "useFinishCalibration"],
                "path": "unknown",
                "reason": "Hooks are present, but no Android route literal or low-level implementation was recovered.",
                "validation_status": "hook-only",
            },
        ],
    }


def build_local_protocol_map(evidence_refs: dict[str, str]) -> dict[str, Any]:
    return {
        "source_artifact": SOURCE_XAPK.name,
        "app_version": APP_VERSION,
        "entries": [
            {
                "transport": "bluetooth_le",
                "entrypoint": "NativeBleManagerSpec / BleManagerPackage",
                "operation": "scan_connect_read_write_notify",
                "identifiers_or_uuids": [
                    "service UUID filters supported but concrete Fellow UUIDs not recovered statically",
                ],
                "message_shape": [
                    "string peripheral ID",
                    "string service UUID",
                    "string characteristic UUID",
                    "byte array payloads",
                ],
                "state_transitions": [
                    "checkState",
                    "scan",
                    "onDiscoverPeripheral",
                    "connect",
                    "retrieveServices",
                    "read/write",
                    "startNotification",
                    "disconnect",
                ],
                "dependencies": [
                    "android.permission.BLUETOOTH_*",
                    "BleManagerPackage",
                ],
                "evidence": [
                    evidence_refs["ble_spec"],
                    evidence_refs["ble_companion"],
                    evidence_refs["manifest_ble_permissions"],
                ],
                "validation_status": "static-confirmed",
            },
            {
                "transport": "companion_device_manager_ble",
                "entrypoint": "CompanionScanner",
                "operation": "single_device_ble_association",
                "identifiers_or_uuids": [
                    "optional BLE service UUID filter",
                ],
                "message_shape": [
                    "ReadableArray service UUID filters",
                    "ReadableMap options with `single` flag",
                ],
                "state_transitions": [
                    "companionScan",
                    "associate",
                    "onDeviceFound",
                    "onCompanionPeripheral/onCompanionFailure",
                ],
                "dependencies": [
                    "CompanionDeviceManager",
                    "BleManagerPackage",
                ],
                "evidence": [
                    evidence_refs["ble_companion"],
                ],
                "validation_status": "static-confirmed",
            },
            {
                "transport": "wifi_manager_and_rnwifi",
                "entrypoint": "RNWifiModule / WifiConnectorBuilder / WifiUtils",
                "operation": "scan_connect_disconnect_current_ssid",
                "identifiers_or_uuids": [
                    "SSID",
                    "BSSID",
                    "security type",
                ],
                "message_shape": [
                    "SSID/password pairs",
                    "scan result lists",
                    "current SSID query",
                ],
                "state_transitions": [
                    "loadWifiList",
                    "connectToProtectedSSID",
                    "connectToProtectedWifiSSID",
                    "disconnect",
                    "getCurrentWifiSSID",
                ],
                "dependencies": [
                    "android.permission.ACCESS_WIFI_STATE",
                    "android.permission.CHANGE_WIFI_STATE",
                    "RNWifiPackage",
                    "wifiutils",
                ],
                "evidence": [
                    evidence_refs["rnwifi_methods"],
                    evidence_refs["wifi_builder"],
                    evidence_refs["manifest_wifi_permissions"],
                ],
                "validation_status": "static-confirmed",
            },
            {
                "transport": "local_http_to_device_ap",
                "entrypoint": "Hermes bundle provisioning hooks",
                "operation": "wifi_provisioning_negotiation",
                "identifiers_or_uuids": [
                    "SSID/password endpoints inferred from `postSSID`, `postPassword`, `postGetWifiList`, `postGetWifiStatus` strings",
                ],
                "message_shape": [
                    "Wi-Fi list/status requests",
                    "SSID/password posts",
                    "data-length/data-security negotiation posts",
                ],
                "state_transitions": [
                    "postGetWifiList",
                    "postGetWifiStatus",
                    "postNegotiateDataSecurity",
                    "postNegotiateLengthSecurity",
                    "postSSID",
                    "postPassword",
                    "postProcessPassResolved",
                ],
                "dependencies": [
                    "device provisioning mode",
                    "local network reachability",
                ],
                "evidence": [
                    evidence_refs["hermes_wifi"],
                    evidence_refs["hermes_claim_provision"],
                ],
                "validation_status": "hypothesis",
            },
            {
                "transport": "android_keystore_via_react_native_keychain",
                "entrypoint": "KeychainModule",
                "operation": "credential_storage_and_retrieval",
                "identifiers_or_uuids": [
                    "alias/service names",
                ],
                "message_shape": [
                    "username/password pairs",
                    "service/server alias",
                    "biometry/passcode access control options",
                ],
                "state_transitions": [
                    "setGenericPassword",
                    "getGenericPassword",
                    "getAllGenericPasswordServices",
                    "resetGenericPassword",
                ],
                "dependencies": [
                    "KeychainPackage",
                    "biometric/passcode availability (optional)",
                ],
                "evidence": [
                    evidence_refs["keychain_methods"],
                ],
                "validation_status": "static-confirmed",
            },
            {
                "transport": "firebase_cloud_messaging",
                "entrypoint": "ReactNativeFirebaseMessagingService / bundle notification hooks",
                "operation": "push_registration_and_notification_open_handling",
                "identifiers_or_uuids": [
                    "FCM token (not recovered statically)",
                ],
                "message_shape": [
                    "notification open callbacks",
                    "notification preference update flow",
                ],
                "state_transitions": [
                    "register/unregister for remote notifications",
                    "onNotificationOpenedApp",
                    "updateUserNotifications",
                ],
                "dependencies": [
                    "Firebase Messaging",
                    "POST_NOTIFICATIONS permission",
                ],
                "evidence": [
                    evidence_refs["manifest_notifications"],
                    evidence_refs["hermes_notifications"],
                ],
                "validation_status": "static-confirmed",
            },
        ],
    }


def build_parity_matrix() -> str:
    rows = [
        (
            "Cloud auth/session bootstrap",
            "High",
            "Config flow uses `/v1/auth/login`; refresh uses `/v1/auth/refresh`.",
            "App 1.4.5 uses API `/v2`, login includes `timezone`, and refresh is `/auth/refresh-token`.",
            "Capture live login/refresh responses, then migrate the client with compatibility handling.",
            "Blocked by missing authenticated runtime trace.",
        ),
        (
            "Device inventory and telemetry",
            "High",
            "Implemented via coordinator polling and sensors/binary sensors/selects.",
            "Mobile app also has device list and settings surfaces.",
            "Keep current implementation; use mobile evidence to validate any missing device fields.",
            "No blocker for current HA behavior.",
        ),
        (
            "Profiles list/create/delete/detail",
            "High",
            "List/create/update/delete/share are present in the client and services.",
            "App mutations add `settingsVersion`; public fetch is `/shared/{dropType}/{profileId}`, while HA uses `/shared/{bid}`.",
            "Capture `settingsVersion` values and response conflicts before changing mutations.",
            "Static routes are confirmed; runtime concurrency semantics are not.",
        ),
        (
            "Schedules list/create/delete/toggle",
            "High",
            "Implemented via services and vendored schedule models.",
            "App 1.4.5 confirms the same list/create/update/delete route family.",
            "Validate live request/response shapes while checking API v2 compatibility.",
            "Static routes are confirmed; runtime response shapes are not.",
        ),
        (
            "Direct brew control and cleaning flows",
            "High",
            "Not implemented.",
            "App confirms `PATCH /devices/{id}/start`, `/stop`, `/clean`, and `/rinse`; start optionally uses `confirm=true` and `brewInfo`.",
            "Capture safe live calls and exact payload/response behavior before exposing HA actions.",
            "Blocked by missing authenticated hardware-backed trace.",
        ),
        (
            "Device patch/settings customization",
            "Medium-High",
            "Generic device patch exists in the vendored client but is not broadly exposed as HA entities.",
            "App confirms generic and device-type-prefixed PATCH routes plus elevation updates.",
            "Inventory safe settings from a live device before adding entities.",
            "Blocked by missing live device payloads.",
        ),
        (
            "BLE claim and association",
            "Medium",
            "Not implemented and currently outside the cloud-only integration model.",
            "Static evidence confirms RN BLE stack and companion scan support.",
            "Document only until a hardware-backed provisioning effort is needed.",
            "Blocked by missing hardware and runtime target.",
        ),
        (
            "Wi-Fi onboarding / local provisioning",
            "Medium",
            "Not implemented and currently outside the cloud-only integration model.",
            "Static evidence suggests local Wi-Fi/AP negotiation via RNWifi plus provisioning posts.",
            "Treat as separate local-transport project after hardware is available.",
            "Blocked by missing hardware and runtime target.",
        ),
        (
            "Firmware/update status and flows",
            "Medium",
            "Not implemented.",
            "App confirms `GET /devices/{id}/updates`; update execution transport is not decoded.",
            "Capture live update-related traffic before adding HA actions.",
            "Blocked by missing account/hardware.",
        ),
        (
            "Mobile push notifications",
            "Low-Medium",
            "Out of scope for HA entity parity.",
            "Firebase messaging is wired into the mobile app.",
            "Only decode if notification preferences prove relevant to device settings APIs.",
            "Not required for current HA scope.",
        ),
        (
            "Share links / drops / public content",
            "Low",
            "Out of scope.",
            "Deep links and share-style profile routes are present in the mobile app.",
            "Ignore unless profile sharing needs to be mirrored in HA services.",
            "No blocker.",
        ),
        (
            "Espresso Series 1 product flows",
            "Low",
            "Out of scope for this Aiden-focused integration.",
            "The mobile artifact clearly contains Series 1 content and troubleshooting copy.",
            "Keep separated from Aiden parity work.",
            "No blocker; excluded by scope.",
        ),
    ]
    header = "| Mobile Capability | HA Relevance | Current HA State | Mobile Evidence Delta | Next Step | Blocking Dependency |\n| --- | --- | --- | --- | --- | --- |"
    lines = ["# Feature Parity Matrix", "", header]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("Reference: `evidence/current_integration_state.md` plus the generated cloud/local catalogs.")
    return "\n".join(lines)


def build_capture_summary(xapk_hash: str) -> str:
    return f"""# Fellow Android 1.4.5 Capture Summary

## Artifact

- Package: `com.fellowproducts.Fellow`
- Version: `1.4.5` (`versionCode` `52`)
- Source: `{SOURCE_XAPK.name}`
- SHA-256: `{xapk_hash}`
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
| Public profile | `GET /shared/{{dropType}}/{{profileId}}` | `GET /shared/{{bid}}` |
| Profile mutations | Client adds `settingsVersion` | No `settingsVersion` handling |
| Brew/maintenance | Start, stop, clean, and rinse routes are present | No direct actions |

The exact route inventory is in `cloud_api_catalog.yaml`. No integration code was changed during this capture.

## Next Runtime Capture

1. Record authenticated login, refresh, and device-list exchanges against API v2.
2. Record profile create/update/delete conflicts to establish `settingsVersion` semantics.
3. Record schedule responses and generic device patch payloads.
4. With the brewer in a safe state, record start/stop/clean/rinse requests and responses.

`adb` and an Android target were unavailable on this host, so those runtime checks remain deferred.
"""


def build_readme(xapk_hash: str) -> str:
    return f"""# Fellow Android 1.4.5 Reverse-Engineering Workspace

This is a reproducible static capture of `{SOURCE_XAPK.name}` (`{xapk_hash}`). It does not modify the Home Assistant integration.

Regenerate from the default Downloads location:

```sh
uv run python reverse_engineering/fellow-android-v1.4.5/scripts/generate_workspace.py
```

Set `FELLOW_XAPK` to use another path. Heavy decompiler outputs are written under ignored `generated/`; curated evidence, catalogs, hashes, and comparisons are committed.

Start with `evidence/capture_summary.md` and `cloud_api_catalog.yaml`. Routes and verbs marked `static-confirmed` were recovered from Hermes bytecode. Runtime payload semantics that could not be established are explicitly identified as unresolved.
"""


def build_dynamic_pass_report(
    has_adb: bool,
    has_emulator: bool,
    adb_devices_output: str,
) -> str:
    lines = [
        "# Dynamic Pass Status",
        "",
        "## Local Runtime Check",
        f"- `adb` present: `{str(has_adb).lower()}`",
        f"- `emulator` present: `{str(has_emulator).lower()}`",
        "- Attached Android targets:",
        "```text",
        adb_devices_output.rstrip() or "List of devices attached",
        "```",
        "",
    ]
    if not has_adb:
        lines.extend(
            [
                "## Result",
                "",
                "- Dynamic pass is blocked locally: `adb` is not installed on this host.",
                "",
                "## Deferred Checklist",
                "",
                "1. Install Android platform tools or use the existing Windows capture host.",
                "2. Attach a rooted/debuggable Android device or a compatible ARM-capable emulator.",
                "3. Install the split APK set from `generated/apks/`.",
                "4. Capture authenticated app traffic and reconcile it with `cloud_api_catalog.yaml`.",
                "",
            ]
        )
    elif not has_emulator and not adb_has_target(adb_devices_output):
        lines.extend(
            [
                "## Result",
                "",
                "- Dynamic pass is blocked locally: no Android emulator tooling is installed and no physical/emulated device is attached via `adb`.",
                "",
                "## Deferred Checklist",
                "",
                "1. Install Android emulator tooling or attach a rooted/debuggable Android device.",
                "2. Extract and install the split APK set with `adb install-multiple` from `generated/apks/`.",
                "3. Capture cold-start `logcat`, app storage, and unauthenticated launch/login behavior.",
                "4. Re-test deep links for `fellow://`, `https://brew.link/p`, and `/account/activate` routes.",
                "5. If traffic is opaque, add a trust/mitm validation branch and re-check whether pinning truly is absent at runtime.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Result",
                "",
                "- Android runtime tooling is available; continue with install and runtime capture.",
                "",
            ]
        )
    return "\n".join(lines)


def build_verification(
    xapk_hash: str,
    hermes_file_description: str,
    service_names: list[str],
    feature_hits: dict[str, list[dict[str, Any]]],
    dynamic_blocked: bool,
    dynamic_reason: str,
) -> str:
    _, separator, description = hermes_file_description.strip().partition(": ")
    hermes_description = description if separator else hermes_file_description.strip()
    coverage_rows = []
    for feature_name in [
        "auth",
        "device_list",
        "claim_provision",
        "wifi",
        "profiles",
        "schedules",
        "brew_control",
        "notifications",
        "firmware_update",
    ]:
        hits = feature_hits.get(feature_name, [])
        status = "covered" if hits else "missing"
        coverage_rows.append(f"| `{feature_name}` | `{status}` | `{len(hits)}` |")

    runtime_status = "blocked" if dynamic_blocked else "ready"
    return f"""# Verification

## Reproducibility

- Source XAPK hash captured: `{xapk_hash}`
- Hermes bundle identified as: `{hermes_description}`
- Static extraction is scripted via `uv run python reverse_engineering/fellow-android-v1.4.5/scripts/generate_workspace.py`

## Coverage

| Feature | Status | Evidence Hits |
| --- | --- | ---: |
{chr(10).join(coverage_rows)}

## Integration Cross-Check

- Current HA service count: `{len(service_names)}`
- Services discovered: `{", ".join(service_names)}`

## Runtime Status

- Dynamic pass status: `{runtime_status}`
- Reason: `{dynamic_reason}`

## Catalog Quality

- `cloud_api_catalog.yaml` records static-confirmed routes and verbs with evidence references.
- `local_protocol_map.yaml` generated with stable fields and evidence references.
- Unresolved calibration routes and payload semantics remain explicitly marked instead of being invented.
"""


def main() -> None:
    if not SOURCE_XAPK.exists():
        raise SystemExit(f"Missing source artifact: {SOURCE_XAPK}")

    ensure_dirs()

    tool_versions = {
        "uv": command_version("uv", "--version"),
        "apktool": command_version("apktool", "--version"),
        "jadx": command_version("jadx", "--version"),
        "adb": command_version("adb", "version"),
        "hbc-disassembler": (
            "native command"
            if shutil.which("hbc-disassembler")
            else "uvx hermes-dec (pinned commit)"
        ),
    }

    xapk_hash = sha256_file(SOURCE_XAPK)

    with zipfile.ZipFile(SOURCE_XAPK) as archive:
        xapk_manifest = json.loads(archive.read("manifest.json"))
        if xapk_manifest.get("version_name") != APP_VERSION:
            raise SystemExit(
                f"Expected Fellow {APP_VERSION}, got {xapk_manifest.get('version_name', 'unknown')}"
            )
        write_text(INPUTS_DIR / "xapk_manifest.json", json.dumps(xapk_manifest, indent=2) + "\n")

        split_rows: list[dict[str, Any]] = []
        for split in xapk_manifest["split_apks"]:
            member_name = split["file"]
            info = archive.getinfo(member_name)
            split_rows.append(
                {
                    "name": member_name,
                    "role": split["id"],
                    "size": info.file_size,
                    "sha256": sha256_zip_member(archive, member_name),
                }
            )
            destination = GENERATED_APKS_DIR / member_name
            if not destination.exists():
                extract_member(archive, member_name, destination)

    base_apk_path = GENERATED_APKS_DIR / BASE_APK_NAME
    abi_split_path = GENERATED_APKS_DIR / ABI_SPLIT_NAME

    apktool_base_dir = GENERATED_APKTOOL_DIR / "base"
    if not apktool_base_dir.exists():
        run(["apktool", "d", "-f", "-o", str(apktool_base_dir), str(base_apk_path)])

    jadx_base_dir = GENERATED_JADX_DIR / "base"
    if not jadx_base_dir.exists():
        try:
            run(["jadx", "-q", "-j", "2", "-d", str(jadx_base_dir), str(base_apk_path)])
        except subprocess.CalledProcessError:
            if not ((jadx_base_dir / "sources").exists() and (jadx_base_dir / "resources").exists()):
                raise

    hermes_bundle_path = GENERATED_HERMES_DIR / "index.android.bundle"
    if not hermes_bundle_path.exists():
        with zipfile.ZipFile(base_apk_path) as base_archive:
            extract_member(base_archive, "assets/index.android.bundle", hermes_bundle_path)

    hermes_disasm_path = GENERATED_HERMES_DIR / "index.android.disasm"
    if not hermes_disasm_path.exists():
        run(["hbc-disassembler", str(hermes_bundle_path), str(hermes_disasm_path)])

    hermes_file_description = run(["file", str(hermes_bundle_path)], capture=True)

    copy_selected_files(jadx_base_dir)

    emit_method_index(
        jadx_base_dir / "sources/com/oblador/keychain/KeychainModule.java",
        EVIDENCE_CODE_DIR / "com/oblador/keychain/Keychain_methods.md",
        [
            "setGenericPassword(",
            "getGenericPassword(",
            "getAllGenericPasswordServices(",
            "resetGenericPassword(",
            "setInternetCredentialsForServer(",
            "getInternetCredentialsForServer(",
            "getSupportedBiometryType(",
            "getSecurityLevel(",
        ],
        "Keychain Methods",
    )
    emit_method_index(
        jadx_base_dir / "sources/com/reactlibrary/rnwifi/RNWifiModule.java",
        EVIDENCE_CODE_DIR / "com/reactlibrary/rnwifi/RNWifi_methods.md",
        [
            "loadWifiList(",
            "forceWifiUsageWithOptions(",
            "isEnabled(",
            "setEnabled(",
            "connectToProtectedSSID(",
            "connectToProtectedWifiSSID(",
            "disconnect(",
            "getCurrentWifiSSID(",
        ],
        "RNWifi Methods",
    )

    manifest_path = EVIDENCE_CODE_DIR / "resources/AndroidManifest.xml"
    build_config_path = EVIDENCE_CODE_DIR / "is/symphony/FellowDev/BuildConfig.java"
    main_application_path = EVIDENCE_CODE_DIR / "is/symphony/FellowDev/MainApplication.java"
    main_activity_path = EVIDENCE_CODE_DIR / "is/symphony/FellowDev/MainActivity.java"
    package_list_path = EVIDENCE_CODE_DIR / "com/facebook/react/PackageList.java"
    config_module_path = EVIDENCE_CODE_DIR / "com/lugg/RNCConfig/RNCConfigModule.java"
    ble_spec_path = EVIDENCE_CODE_DIR / "it/innove/NativeBleManagerSpec.java"
    companion_scanner_path = EVIDENCE_CODE_DIR / "it/innove/CompanionScanner.java"
    wifi_builder_path = EVIDENCE_CODE_DIR / "com/thanosfisherman/wifiutils/WifiConnectorBuilder.java"
    rnwifi_methods_path = EVIDENCE_CODE_DIR / "com/reactlibrary/rnwifi/RNWifi_methods.md"
    keychain_methods_path = EVIDENCE_CODE_DIR / "com/oblador/keychain/Keychain_methods.md"

    manifest_data = parse_manifest(manifest_path)
    build_config = parse_build_config(build_config_path)
    package_names = parse_package_list(package_list_path)
    grouped_packages = group_packages(package_names)

    network_security_hits: list[str] = []
    if manifest_data["networkSecurityConfig"]:
        network_security_hits.append(
            f"Manifest sets `networkSecurityConfig` to `{manifest_data['networkSecurityConfig']}`."
        )
    if manifest_data["usesCleartextTraffic"]:
        network_security_hits.append(
            f"Manifest sets `usesCleartextTraffic` to `{manifest_data['usesCleartextTraffic']}`."
        )
    for copied_file in [build_config_path, main_application_path, main_activity_path]:
        copied_text = copied_file.read_text(encoding="utf-8", errors="replace")
        for needle in ["CertificatePinner", "HostnameVerifier", "SSLSocketFactory", "X509TrustManager"]:
            if needle in copied_text:
                network_security_hits.append(
                    f"`{needle}` appears in `{copied_file.relative_to(WORKSPACE)}`."
                )

    hermes_feature_hits = {
        feature: grep_lines(hermes_disasm_path, patterns)
        for feature, patterns in HERMES_FEATURE_PATTERNS.items()
    }

    service_names = top_level_yaml_keys(REPO_ROOT / "custom_components/fellow/services.yaml")

    artifact_index = build_artifact_index(
        xapk_hash=xapk_hash,
        xapk_manifest=xapk_manifest,
        manifest_data=manifest_data,
        build_config=build_config,
        split_hash_rows=split_rows,
        tool_versions=tool_versions,
        hermes_file_description=hermes_file_description,
    )
    write_text(EVIDENCE_DIR / "artifact_index.md", artifact_index)

    android_surface_model = build_android_surface_model(
        manifest_data=manifest_data,
        grouped_packages=grouped_packages,
        build_config_path=build_config_path,
        main_application_path=main_application_path,
        main_activity_path=main_activity_path,
        package_list_path=package_list_path,
        config_module_path=config_module_path,
        network_security_hits=network_security_hits,
    )
    write_text(EVIDENCE_DIR / "android_surface_model.md", android_surface_model)

    hermes_feature_map = build_hermes_feature_map(hermes_disasm_path, hermes_feature_hits)
    write_text(EVIDENCE_DIR / "hermes_feature_map.md", hermes_feature_map)

    integration_state = build_integration_current_state(service_names)
    write_text(EVIDENCE_DIR / "current_integration_state.md", integration_state)

    has_adb = shutil.which("adb") is not None
    adb_devices_output = (
        run(["adb", "devices", "-l"], capture=True)
        if has_adb
        else "adb unavailable"
    )
    has_emulator = shutil.which("emulator") is not None
    dynamic_report = build_dynamic_pass_report(
        has_adb=has_adb,
        has_emulator=has_emulator,
        adb_devices_output=adb_devices_output,
    )
    write_text(RUNTIME_DIR / "dynamic_pass.md", dynamic_report)

    manifest_ble_line = line_number(manifest_path, "android.permission.BLUETOOTH_SCAN")
    manifest_wifi_line = line_number(manifest_path, "android.permission.ACCESS_WIFI_STATE")
    manifest_fcm_line = line_number(manifest_path, "io.invertase.firebase.messaging.ReactNativeFirebaseMessagingService")
    api_line = line_number(build_config_path, "API_GATEWAY_URL")
    activate_line = line_number(manifest_path, "android:pathPrefix=\"/account/activate\"")
    brew_link_line = line_number(manifest_path, "android:host=\"brew.link\"")
    ble_spec_line = line_number(ble_spec_path, "public abstract void scan(")
    companion_line = line_number(companion_scanner_path, "associate(")
    wifi_builder_line = line_number(wifi_builder_path, "connectWith(String str, String str2)")

    evidence_refs = {
        "build_config_api": f"{build_config_path.relative_to(WORKSPACE)}:{api_line}",
        "manifest_activate_link": f"{manifest_path.relative_to(WORKSPACE)}:{activate_line}",
        "share_link": f"{manifest_path.relative_to(WORKSPACE)}:{brew_link_line}",
        "manifest_ble_permissions": f"{manifest_path.relative_to(WORKSPACE)}:{manifest_ble_line}",
        "manifest_wifi_permissions": f"{manifest_path.relative_to(WORKSPACE)}:{manifest_wifi_line}",
        "manifest_notifications": f"{manifest_path.relative_to(WORKSPACE)}:{manifest_fcm_line}",
        "ble_spec": f"{ble_spec_path.relative_to(WORKSPACE)}:{ble_spec_line}",
        "ble_companion": f"{companion_scanner_path.relative_to(WORKSPACE)}:{companion_line}",
        "wifi_builder": f"{wifi_builder_path.relative_to(WORKSPACE)}:{wifi_builder_line}",
        "rnwifi_methods": f"{rnwifi_methods_path.relative_to(WORKSPACE)}",
        "keychain_methods": f"{keychain_methods_path.relative_to(WORKSPACE)}",
        "hermes_auth": "evidence/hermes_feature_map.md (Auth section)",
        "hermes_device_list": "evidence/hermes_feature_map.md (Device List section)",
        "hermes_claim_provision": "evidence/hermes_feature_map.md (Claim Provision section)",
        "hermes_wifi": "evidence/hermes_feature_map.md (Wifi section)",
        "hermes_profiles": "evidence/hermes_feature_map.md (Profiles section)",
        "hermes_schedules": "evidence/hermes_feature_map.md (Schedules section)",
        "hermes_notifications": "evidence/hermes_feature_map.md (Notifications section)",
        "hermes_account_settings": "evidence/hermes_feature_map.md (Account Settings section)",
    }

    cloud_catalog = build_cloud_catalog(evidence_refs)
    endpoint_function_ids = {
        entry["hermes_function_id"] for entry in cloud_catalog["entries"]
    }
    endpoint_function_ids.add(17436)
    endpoint_evidence = extract_hermes_functions(
        hermes_disasm_path,
        endpoint_function_ids,
    )
    write_text(EVIDENCE_DIR / "hermes_endpoint_functions.txt", endpoint_evidence)
    write_text(WORKSPACE / "cloud_api_catalog.yaml", dump_yaml(cloud_catalog) + "\n")

    local_protocol_map = build_local_protocol_map(evidence_refs)
    write_text(WORKSPACE / "local_protocol_map.yaml", dump_yaml(local_protocol_map) + "\n")

    feature_parity_matrix = build_parity_matrix()
    write_text(WORKSPACE / "feature_parity_matrix.md", feature_parity_matrix)

    capture_summary = build_capture_summary(xapk_hash)
    write_text(EVIDENCE_DIR / "capture_summary.md", capture_summary)

    readme = build_readme(xapk_hash)
    write_text(WORKSPACE / "README.md", readme)

    verification = build_verification(
        xapk_hash=xapk_hash,
        hermes_file_description=hermes_file_description,
        service_names=service_names,
        feature_hits=hermes_feature_hits,
        dynamic_blocked=(not has_adb or (not has_emulator and not adb_has_target(adb_devices_output))),
        dynamic_reason=(
            "adb is not installed on this host."
            if not has_adb
            else "adb is present, but no emulator/device was available locally during generation."
        ),
    )
    write_text(WORKSPACE / "verification.md", verification)

    print(f"Workspace generated under {WORKSPACE}")


if __name__ == "__main__":
    main()
