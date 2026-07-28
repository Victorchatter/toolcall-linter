"""Render validation violations as text or JSON."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from typing import Iterable, TextIO


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    tool: str
    severity: str
    message: str
    schema_path: str | None = None


def report_text(violations: Iterable[Violation], stream: TextIO = sys.stdout) -> None:
    for v in violations:
        schema_suffix = f" ({v.schema_path})" if v.schema_path else ""
        stream.write(f"{v.file}:{v.line} {v.tool}: {v.message}{schema_suffix}\n")


def report_json(
    violations: Iterable[Violation], stream: TextIO = sys.stdout
) -> None:
    violation_list = list(violations)
    payload = {
        "ok": not violation_list,
        "violation_count": len(violation_list),
        "violations": [asdict(v) for v in violation_list],
    }
    json.dump(payload, stream, indent=2)
    stream.write("\n")


def report_sarif(
    violations: Iterable[Violation], stream: TextIO = sys.stdout, *, tool_name: str = "toolcall-linter"
) -> None:
    violation_list = list(violations)
    results = []
    for v in violation_list:
        result: dict = {
            "ruleId": v.tool,
            "level": "error" if v.severity == "error" else "warning",
            "message": {"text": v.message},
            "locations": [],
        }
        if v.file or v.line:
            physical = {"artifactLocation": {"uri": v.file or "transcript"}}
            if v.line:
                physical["region"] = {"startLine": v.line}
            result["locations"].append({"physicalLocation": physical})
        results.append(result)

    payload = {
        "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": tool_name, "informationUri": "https://github.com/Victorchatter/toolcall-linter"}},
                "results": results,
            }
        ],
    }
    json.dump(payload, stream, indent=2)
    stream.write("\n")
