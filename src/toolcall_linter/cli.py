"""CLI entry point for toolcall-linter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .reporter import Violation, report_json, report_text
from .schema_source import load_schema_source
from .transcript import parse_transcript
from .validator import validate_calls


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="toolcall-linter",
        description="Cross-check agent transcript tool calls against declared schemas.",
    )
    parser.add_argument("transcript", help="Path to the transcript file")
    parser.add_argument(
        "--tools",
        required=True,
        help="Schema source: tools.json path, mcp-stdio:<cmd>, or mcp-http:<url>",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    args = parser.parse_args(argv)

    transcript_path = Path(args.transcript)
    try:
        schemas = load_schema_source(args.tools)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: failed to load schema source: {exc}", file=sys.stderr)
        return 2

    try:
        calls = list(parse_transcript(transcript_path))
    except Exception as exc:
        print(f"error: failed to parse transcript: {exc}", file=sys.stderr)
        return 2

    violations = validate_calls(calls, schemas)
    # Attach the transcript file path to each violation for reporting.
    violations = [
        Violation(
            file=str(transcript_path),
            line=v.line,
            tool=v.tool,
            severity=v.severity,
            message=v.message,
            schema_path=v.schema_path,
        )
        for v in violations
    ]

    if args.format == "json":
        report_json(violations)
    else:
        report_text(violations)

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
