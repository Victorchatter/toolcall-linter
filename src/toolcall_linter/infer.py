"""Infer JSON Schemas for tool calls from a transcript."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .transcript import ToolCall, parse_transcript


def infer_schema(transcript_paths: Iterable[str | Path]) -> dict:
    """Build a tools.json-style schema by inspecting actual tool calls in tapes.

    For every tool name observed, the returned schema contains a JSON Schema
    object that:
      - unions all argument keys ever seen for that tool,
      - marks a key as required only when it appears in every call,
      - infers JSON Schema types from the observed values,
      - emits a string enum when a property has <=10 distinct string values,
      - forbids additionalProperties, and
      - records the source transcript paths in _meta.inferred_from.
    """
    paths = [Path(p) for p in transcript_paths]
    calls: list[ToolCall] = []
    for path in paths:
        calls.extend(parse_transcript(path))

    by_tool: dict[str, list[dict]] = {}
    for call in calls:
        by_tool.setdefault(call.tool, []).append(call.arguments)

    tools = [
        _infer_tool_schema(tool_name, args_list, paths)
        for tool_name, args_list in sorted(by_tool.items())
    ]
    return {"tools": tools}


def _infer_tool_schema(
    tool_name: str, args_list: list[dict], source_paths: list[Path]
) -> dict:
    properties: dict[str, dict] = {}
    required: set[str] = set()

    if args_list:
        required = set(args_list[0].keys())
        for args in args_list[1:]:
            required &= set(args.keys())

    all_keys: set[str] = set()
    values_by_key: dict[str, list[Any]] = {}
    for args in args_list:
        for key, value in args.items():
            all_keys.add(key)
            values_by_key.setdefault(key, []).append(value)

    for key in sorted(all_keys):
        properties[key] = _infer_property_schema(tool_name, key, values_by_key[key])

    return {
        "name": tool_name,
        "description": f"Inferred schema for {tool_name}.",
        "inputSchema": {
            "type": "object",
            "description": f"Inferred input schema for {tool_name}.",
            "properties": properties,
            "required": sorted(required),
            "additionalProperties": False,
        },
        "_meta": {
            "inferred_from": [str(p) for p in source_paths],
        },
    }


def _infer_property_schema(tool_name: str, key: str, values: list[Any]) -> dict:
    schema: dict[str, Any] = {
        "description": f"Inferred argument {key!r} for {tool_name}.",
    }

    types: set[str] = set()
    string_values: set[str] = set()
    all_strings = True

    for value in values:
        t = _json_schema_type(value)
        types.add(t)
        if isinstance(value, str):
            string_values.add(value)
        else:
            all_strings = False

    # If both integer and number are observed, collapse to number only.
    if "integer" in types and "number" in types:
        types.discard("integer")

    type_list = sorted(types)
    if len(type_list) == 1:
        schema["type"] = type_list[0]
    elif type_list:
        schema["type"] = type_list

    if all_strings and 1 <= len(string_values) <= 10:
        schema["enum"] = sorted(string_values)

    return schema


def _json_schema_type(value: Any) -> str:
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
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"
