"""Synthetic end-to-end test for toolcall-linter."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


SARIF_SCHEMA_URL = (
    "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json"
)


def _sarif_schema_path() -> str:
    """Return a locally cached SARIF 2.1.0 JSON schema path, downloading if needed."""
    cache_dir = Path(tempfile.gettempdir()) / "toolcall-linter-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "sarif-2-1-0.json"
    if not path.exists():
        with urllib.request.urlopen(SARIF_SCHEMA_URL, timeout=30) as resp:
            path.write_bytes(resp.read())
    return str(path)


def _validate_sarif(payload: dict) -> None:
    import jsonschema

    schema_path = _sarif_schema_path()
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.validate(instance=payload, schema=schema)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        tools_path = tmp / "tools.json"
        transcript_path = tmp / "transcript.jsonl"

        tools = {
            "tools": [
                {
                    "name": "read_file",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "limit": {"type": "integer"},
                        },
                        "required": ["file_path"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "delete_file",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "confirm": {"type": "string", "enum": ["yes", "no"]},
                        },
                        "required": ["file_path", "confirm"],
                        "additionalProperties": False,
                    },
                },
            ]
        }
        tools_path.write_text(json.dumps(tools), encoding="utf-8")

        transcript = [
            # valid
            {"type": "tool_use", "name": "read_file", "input": {"file_path": "/etc/passwd"}},
            # missing required
            {"type": "tool_use", "name": "read_file", "input": {"limit": 10}},
            # wrong type
            {"type": "tool_use", "name": "read_file", "input": {"file_path": 123}},
            # extra arg
            {"type": "tool_use", "name": "read_file", "input": {"file_path": "/x", "encoding": "utf-8"}},
            # undefined tool
            {"type": "tool_use", "name": "frobnicate", "input": {"x": 1}},
            # bad enum
            {"type": "tool_use", "name": "delete_file", "input": {"file_path": "/x", "confirm": "maybe"}},
        ]
        transcript_path.write_text(
            "\n".join(json.dumps(line) for line in transcript) + "\n", encoding="utf-8"
        )

        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent / "src")
        result = subprocess.run(
            [sys.executable, "-m", "toolcall_linter.cli", str(transcript_path), "--tools", str(tools_path), "--format", "json"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent,
            env=env,
        )

        if result.returncode == 0:
            print("FAIL: expected nonzero exit code", file=sys.stderr)
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            return 1

        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError:
            print("FAIL: stdout is not valid JSON", file=sys.stderr)
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            return 1

        if output.get("ok"):
            print("FAIL: expected ok=false", file=sys.stderr)
            return 1

        all_messages = " ".join(v["message"] for v in output.get("violations", []))
        all_messages_lower = all_messages.lower()
        print(f"Found {len(output.get('violations', []))} violations")
        for v in output.get("violations", []):
            print(" -", v["message"])

        checks = [
            ("missing required", "required" in all_messages_lower),
            ("wrong type", "'string'" in all_messages_lower or "integer" in all_messages_lower),
            ("extra arg / additionalProperties", "additional" in all_messages_lower),
            ("undefined tool", "frobnicate" in all_messages_lower),
            ("bad enum", "maybe" in all_messages_lower or "enum" in all_messages_lower),
        ]
        failed = [name for name, ok in checks if not ok]
        if failed:
            print("FAIL: missing expected violation classes:", failed, file=sys.stderr)
            return 1

        # SARIF output must be valid and include results with ruleId + location.
        sarif_result = subprocess.run(
            [sys.executable, "-m", "toolcall_linter.cli", str(transcript_path), "--tools", str(tools_path), "--format", "sarif"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent,
            env=env,
        )
        if sarif_result.returncode == 0:
            print("FAIL: expected nonzero SARIF exit code", file=sys.stderr)
            return 1
        try:
            sarif = json.loads(sarif_result.stdout)
        except json.JSONDecodeError:
            print("FAIL: SARIF stdout is not valid JSON", file=sys.stderr)
            print(sarif_result.stdout, file=sys.stderr)
            return 1
        try:
            _validate_sarif(sarif)
        except Exception as exc:
            print(f"FAIL: SARIF output failed schema validation: {exc}", file=sys.stderr)
            print(sarif_result.stdout, file=sys.stderr)
            return 1
        results = sarif.get("runs", [{}])[0].get("results", [])
        if not results:
            print("FAIL: SARIF run has no results", file=sys.stderr)
            return 1
        for r in results:
            if not r.get("ruleId"):
                print("FAIL: SARIF result missing ruleId", file=sys.stderr)
                return 1
            locs = r.get("locations", [])
            if not locs or not locs[0].get("physicalLocation"):
                print("FAIL: SARIF result missing physicalLocation", file=sys.stderr)
                return 1

        print("PASS")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
