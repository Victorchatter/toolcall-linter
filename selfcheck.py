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


def _run_selfcheck() -> int:
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

        # --- Infer schema tests ------------------------------------------------
        clean_transcript_path = tmp / "clean-transcript.jsonl"
        inferred_path = tmp / "inferred-tools.json"
        clean_transcript = [
            {"type": "tool_use", "name": "read_file", "input": {"file_path": "/etc/passwd"}},
            {"type": "tool_use", "name": "read_file", "input": {"file_path": "/x", "limit": 10}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "git status", "description": "Check status"}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
        ]
        clean_transcript_path.write_text(
            "\n".join(json.dumps(line) for line in clean_transcript) + "\n",
            encoding="utf-8",
        )

        infer_result = subprocess.run(
            [sys.executable, "-m", "toolcall_linter.cli", "infer", str(clean_transcript_path), "-o", str(inferred_path), "--pretty"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent,
            env=env,
        )
        if infer_result.returncode != 0:
            print("FAIL: infer command returned nonzero exit code", file=sys.stderr)
            print(infer_result.stdout, file=sys.stderr)
            print(infer_result.stderr, file=sys.stderr)
            return 1
        if "OK" not in infer_result.stdout:
            print("FAIL: infer command did not report OK", file=sys.stderr)
            print(infer_result.stdout, file=sys.stderr)
            return 1

        try:
            inferred = json.loads(inferred_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"FAIL: inferred schema is not valid JSON: {exc}", file=sys.stderr)
            return 1

        tools = inferred.get("tools", [])
        if len(tools) != 2:
            print(f"FAIL: expected 2 inferred tools, got {len(tools)}", file=sys.stderr)
            return 1

        names = {tool.get("name") for tool in tools}
        if names != {"read_file", "Bash"}:
            print(f"FAIL: expected tools read_file and Bash, got {names}", file=sys.stderr)
            return 1

        by_name = {tool["name"]: tool for tool in tools}
        for name, tool in by_name.items():
            schema = tool.get("inputSchema", {})
            if schema.get("type") != "object":
                print(f"FAIL: {name} inputSchema type is not object", file=sys.stderr)
                return 1
            if schema.get("additionalProperties") is not False:
                print(f"FAIL: {name} inputSchema does not forbid additionalProperties", file=sys.stderr)
                return 1
            if not isinstance(schema.get("properties"), dict):
                print(f"FAIL: {name} inputSchema has no properties dict", file=sys.stderr)
                return 1
            if not isinstance(schema.get("required"), list):
                print(f"FAIL: {name} inputSchema has no required list", file=sys.stderr)
                return 1
            if not isinstance(tool.get("_meta", {}).get("inferred_from"), list):
                print(f"FAIL: {name} missing _meta.inferred_from list", file=sys.stderr)
                return 1

        read_file_required = set(by_name["read_file"]["inputSchema"]["required"])
        bash_required = set(by_name["Bash"]["inputSchema"]["required"])
        if read_file_required != {"file_path"}:
            print(f"FAIL: read_file required mismatch: {read_file_required}", file=sys.stderr)
            return 1
        if bash_required != {"command"}:
            print(f"FAIL: Bash required mismatch: {bash_required}", file=sys.stderr)
            return 1

        if by_name["read_file"]["inputSchema"]["properties"]["file_path"].get("type") != "string":
            print("FAIL: read_file.file_path type is not string", file=sys.stderr)
            return 1
        if by_name["Bash"]["inputSchema"]["properties"]["command"].get("type") != "string":
            print("FAIL: Bash.command type is not string", file=sys.stderr)
            return 1
        if by_name["read_file"]["inputSchema"]["properties"]["limit"].get("type") != "integer":
            print("FAIL: read_file.limit type is not integer", file=sys.stderr)
            return 1

        # Re-run linter with inferred schema; the source tape should produce no violations.
        revalidate_result = subprocess.run(
            [sys.executable, "-m", "toolcall_linter.cli", str(clean_transcript_path), "--tools", str(inferred_path), "--format", "json"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent,
            env=env,
        )
        if revalidate_result.returncode != 0:
            print("FAIL: re-validation with inferred schema returned nonzero exit code", file=sys.stderr)
            print(revalidate_result.stdout, file=sys.stderr)
            print(revalidate_result.stderr, file=sys.stderr)
            return 1
        try:
            revalidate_output = json.loads(revalidate_result.stdout)
        except json.JSONDecodeError:
            print("FAIL: re-validation stdout is not valid JSON", file=sys.stderr)
            print(revalidate_result.stdout, file=sys.stderr)
            return 1
        if not revalidate_output.get("ok") or revalidate_output.get("violation_count", -1) != 0:
            print("FAIL: expected no violations when validating source tape with inferred schema", file=sys.stderr)
            print(revalidate_result.stdout, file=sys.stderr)
            return 1

        print("PASS")
        return 0


def _check_precommit_hook() -> int:
    """If pre-commit is installed, verify the local hook definition is usable."""
    try:
        if subprocess.run(["pre-commit", "--version"], capture_output=True).returncode != 0:
            print("SKIP: pre-commit not installed")
            return 0
    except FileNotFoundError:
        print("SKIP: pre-commit not installed")
        return 0

    repo_root = Path(__file__).resolve().parent
    result = subprocess.run(
        ["pre-commit", "try-repo", str(repo_root), "toolcall-linter", "--all-files"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    # The hook may fail because the example transcript has violations; we only
    # care that the hook installed and ran without a configuration error.
    if "toolcall-linter" not in result.stdout and "toolcall-linter" not in result.stderr:
        print("FAIL: pre-commit try-repo did not execute the toolcall-linter hook", file=sys.stderr)
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        return 1
    print("pre-commit hook usable")
    return 0


def main() -> int:
    rc = _run_selfcheck()
    if rc != 0:
        return rc
    return _check_precommit_hook()


if __name__ == "__main__":
    raise SystemExit(main())
