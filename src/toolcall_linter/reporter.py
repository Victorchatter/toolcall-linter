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
