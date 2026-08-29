# /// script
# requires-python = ">=3.11"
# dependencies = ["mitmproxy==12.2.3"]
# ///

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from mitmproxy import http, io

WORKSPACE = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = WORKSPACE / "generated" / "runtime-capture" / "fellow-api-1.4.5.mitm"
DEFAULT_OUTPUT = WORKSPACE / "runtime" / "sanitized_api_capture.json"
API_HOST = "l8qtmnc692.execute-api.us-west-2.amazonaws.com"

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"^[^/@]+@[^/@]+$")
DYNAMIC_PARENTS = {"devices", "profiles", "schedules"}
DEVICE_ACTIONS = {
    "claim-certificate",
    "factoryReset",
    "provision",
    "share",
    "start",
    "stop",
    "updates",
}

JsonValue = Any
Schema = dict[str, Any]


def scalar_type(value: JsonValue) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    raise TypeError(f"Unsupported scalar: {type(value).__name__}")


def merge_schemas(schemas: list[Schema]) -> Schema:
    unique_types: set[str] = set()
    for schema in schemas:
        schema_types = schema["type"]
        if isinstance(schema_types, list):
            unique_types.update(schema_types)
        else:
            unique_types.add(schema_types)
    ordered_types = sorted(unique_types)
    if len(ordered_types) != 1:
        return {"type": ordered_types}

    schema_type = ordered_types[0]
    if schema_type != "object":
        return schemas[0]

    merged_properties: dict[str, Schema] = {}
    property_counts: dict[str, int] = {}
    for schema in schemas:
        for name, property_schema in schema["properties"].items():
            property_counts[name] = property_counts.get(name, 0) + 1
            existing = merged_properties.get(name)
            if existing is None:
                merged_properties[name] = property_schema
            elif existing != property_schema:
                merged_properties[name] = merge_schemas([existing, property_schema])

    for name, count in property_counts.items():
        if count != len(schemas):
            merged_properties[name] = {**merged_properties[name], "optional": True}

    return {
        "type": "object",
        "properties": dict(sorted(merged_properties.items())),
    }


def schema_for(value: JsonValue) -> Schema:
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {
                key: schema_for(child) for key, child in sorted(value.items())
            },
        }
    if isinstance(value, list):
        return {
            "type": "array",
            "items": merge_schemas([schema_for(item) for item in value])
            if value
            else None,
        }
    return {"type": scalar_type(value)}


def json_schema(message: http.Message | None) -> Schema | None:
    if message is None or not message.content:
        return None
    try:
        value: JsonValue = json.loads(message.get_text(strict=False))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"type": "non-json"}
    return schema_for(value)


def sanitize_path(raw_path: str) -> str:
    segments = [unquote(segment) for segment in urlsplit(raw_path).path.split("/")]
    sanitized: list[str] = []
    for index, segment in enumerate(segments):
        previous = segments[index - 1] if index else ""
        is_dynamic_child = previous in DYNAMIC_PARENTS and not (
            previous == "devices" and segment in DEVICE_ACTIONS
        )
        looks_sensitive = (
            EMAIL_PATTERN.match(segment) is not None
            or UUID_PATTERN.match(segment) is not None
            or (
                len(segment) >= 16 and any(character.isdigit() for character in segment)
            )
        )
        if segment and (is_dynamic_child or looks_sensitive):
            sanitized.append("{id}")
        else:
            sanitized.append(segment)
    return "/".join(sanitized)


def summarize_flow(flow: http.HTTPFlow) -> dict[str, Any]:
    response = flow.response
    query_names = sorted(
        {
            name
            for name, _value in parse_qsl(
                urlsplit(flow.request.path).query, keep_blank_values=True
            )
        }
    )
    return {
        "method": flow.request.method,
        "path": sanitize_path(flow.request.path),
        "query_names": query_names,
        "auth": "bearer" if "authorization" in flow.request.headers else "public",
        "request_content_type": flow.request.headers.get("content-type"),
        "request_schema": json_schema(flow.request),
        "status": response.status_code if response else None,
        "response_content_type": response.headers.get("content-type")
        if response
        else None,
        "response_schema": json_schema(response),
    }


def read_api_flows(path: Path) -> Iterable[http.HTTPFlow]:
    with path.open("rb") as capture:
        for flow in io.FlowReader(capture).stream():
            if isinstance(flow, http.HTTPFlow) and flow.request.host == API_HOST:
                yield flow


def deduplicate(summaries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    deduplicated: dict[str, dict[str, Any]] = {}
    for summary in summaries:
        key = json.dumps(summary, sort_keys=True, separators=(",", ":"))
        existing = deduplicated.get(key)
        if existing is None:
            deduplicated[key] = {**summary, "observations": 1}
        else:
            existing["observations"] += 1
    return sorted(
        deduplicated.values(),
        key=lambda item: (item["path"], item["method"], item["status"] or 0),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a sensitive mitmproxy capture into value-free API schemas."
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    entries = deduplicate(summarize_flow(flow) for flow in read_api_flows(args.input))
    result = {
        "app_version": "1.4.5",
        "api_host": API_HOST,
        "privacy": "Schemas and field names only; all scalar values are omitted.",
        "entries": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} sanitized exchange schemas to {args.output}")


if __name__ == "__main__":
    main()
