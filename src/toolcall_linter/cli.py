"""CLI entry point for toolcall-linter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .infer import infer_schema
from .reporter import Violation, report_json, report_sarif, report_text
from .schema_source import _extract_schemas, load_schema_source
from .transcript import parse_transcript
from .validator import validate_calls


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    if argv and argv[0] == "infer":
        return _main_infer(argv[1:])
    return _main_lint(argv)


def _main_lint(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="toolcall-linter",
        description="Cross-check agent transcript tool calls against declared schemas.",
    )
    parser.add_argument(
        "transcript",
        nargs="+",
        help="Path(s) to one or more transcript files (JSONL or JSON array)",
    )
    parser.add_argument(
        "--tools",
        required=True,
        help="Schema source: tools.json path, mcp-stdio:<cmd>, or mcp-http:<url>",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "sarif"],
        default="text",
        help="Output format (default: text)",
    )

    args = parser.parse_args(argv)

    try:
        schemas = load_schema_source(args.tools)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: failed to load schema source: {exc}", file=sys.stderr)
        return 2

    all_violations: list[Violation] = []
    for transcript_path in args.transcript:
        path = Path(transcript_path)
        try:
            calls = list(parse_transcript(path))
        except Exception as exc:
            print(f"error: failed to parse transcript {path}: {exc}", file=sys.stderr)
            return 2

        violations = validate_calls(calls, schemas)
        # Attach the transcript file path to each violation for reporting.
        all_violations.extend(
            Violation(
                file=str(path),
                line=v.line,
                tool=v.tool,
                severity=v.severity,
                message=v.message,
                schema_path=v.schema_path,
            )
            for v in violations
        )

    if args.format == "json":
        report_json(all_violations)
    elif args.format == "sarif":
        report_sarif(all_violations)
    else:
        report_text(all_violations)

    return 1 if all_violations else 0


def _main_infer(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="toolcall-linter infer",
        description="Infer tool schemas from one or more transcripts.",
    )
    parser.add_argument(
        "transcript",
        nargs="+",
        help="Path(s) to transcript files (JSONL or JSON array)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Path to write the inferred tools.json schema",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Write formatted JSON instead of compact JSON",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip validating the inferred schema against the source transcript(s)",
    )

    args = parser.parse_args(argv)

    transcript_paths = [Path(p) for p in args.transcript]
    for path in transcript_paths:
        if not path.exists():
            print(f"error: transcript not found: {path}", file=sys.stderr)
            return 2

    try:
        inferred = infer_schema(transcript_paths)
    except Exception as exc:
        print(f"error: failed to infer schema: {exc}", file=sys.stderr)
        return 2

    try:
        output_path = Path(args.output)
        indent = 2 if args.pretty else None
        output_path.write_text(
            json.dumps(inferred, indent=indent, sort_keys=False) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"error: failed to write schema: {exc}", file=sys.stderr)
        return 2

    if args.no_validate:
        print(f"Inferred schema written to {output_path}")
        return 0

    schemas = _extract_schemas(inferred)
    all_violations: list[Violation] = []
    for path in transcript_paths:
        try:
            calls = list(parse_transcript(path))
        except Exception as exc:
            print(f"error: failed to parse transcript {path}: {exc}", file=sys.stderr)
            return 2
        violations = validate_calls(calls, schemas)
        all_violations.extend(
            Violation(
                file=str(path),
                line=v.line,
                tool=v.tool,
                severity=v.severity,
                message=v.message,
                schema_path=v.schema_path,
            )
            for v in violations
        )

    if all_violations:
        print(f"Found {len(all_violations)} violation(s) when validating inferred schema")
        for v in all_violations:
            print(f"{v.file}:{v.line} {v.tool}: {v.message}")
        return 1

    print(f"OK: inferred schema validates against {len(transcript_paths)} transcript(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
