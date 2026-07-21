"""Validate tool calls against a schema mapping."""

from __future__ import annotations

import jsonschema

from .reporter import Violation
from .transcript import ToolCall


def validate_calls(
    calls: list[ToolCall], schemas: dict[str, dict]
) -> list[Violation]:
    violations: list[Violation] = []
    for call in calls:
        schema = schemas.get(call.tool)
        if schema is None:
            violations.append(
                Violation(
                    file="",
                    line=call.line,
                    tool=call.tool,
                    severity="error",
                    message=f"tool '{call.tool}' is not declared in schema source",
                )
            )
            continue
        violations.extend(_validate_one(call, schema))
    return violations


def _validate_one(call: ToolCall, schema: dict) -> list[Violation]:
    violations: list[Violation] = []

    # Ensure the schema is an object schema with default strict additionalProperties.
    effective_schema = dict(schema)
    if effective_schema.get("type") is None:
        effective_schema.setdefault("type", "object")
    # ponytail: default to strict args; users can opt out by setting additionalProperties in their schema.
    effective_schema.setdefault("additionalProperties", False)

    try:
        jsonschema.validate(instance=call.arguments, schema=effective_schema)
    except jsonschema.ValidationError as exc:
        violations.append(
            Violation(
                file="",
                line=call.line,
                tool=call.tool,
                severity="error",
                message=_humanize_error(exc),
                schema_path=".".join(str(p) for p in exc.absolute_path),
            )
        )
    return violations


def _humanize_error(exc: jsonschema.ValidationError) -> str:
    # jsonschema messages are already decent; we just strip redundant prefixes.
    msg = exc.message
    if msg.startswith("Failed validating"):
        # Fallback to the validator-specific message.
        msg = exc.message
    return msg
