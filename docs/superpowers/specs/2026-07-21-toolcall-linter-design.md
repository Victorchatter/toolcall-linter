# toolcall-linter Design Spec

**Date:** 2026-07-21  
**Status:** locked  
**Scope:** v1 — static tools.json + live MCP tools/list, JSON-schema arg validation, undefined-tool detection, text/JSON output.

## 1. Goal
A local, offline, read-only CLI linter that cross-checks an agent transcript's tool calls against declared tool schemas. It flags:

1. Calls to an undeclared tool name.
2. Missing required arguments.
3. Argument values that fail the JSON Schema (type, enum, range, pattern, etc.).
4. Extra arguments not declared in the schema (`additionalProperties: false` is the default).

## 2. CLI

```bash
toolcall-linter <transcript> --tools <source> [--format text|json]
```

- `<transcript>` — file path. Supports Claude Code JSONL and OpenAI messages JSON.
- `--tools <source>` — one of:
  - path to a static `tools.json` file,
  - `mcp-stdio:<command>` to spawn an MCP server and call `tools/list`,
  - `mcp-http:<url>` to query an MCP server over HTTP/SSE (uses `tools/list` endpoint).
- `--format text|json` — defaults to `text`.
- Exit code: `0` if no violations, `1` if violations found, `2` for CLI/config errors.

## 3. Tool schema model

A schema source resolves to a flat map of `tool_name → JSON Schema input schema`.

```python
schemas: dict[str, dict] = {
    "read_file": {
        "type": "object",
        "properties": {"file_path": {"type": "string"}},
        "required": ["file_path"],
        "additionalProperties": False,
    },
    ...
}
```

For MCP servers, tool names may be namespaced as `server:tool` when multiple servers are involved. v1 only supports a single `--tools` source, so namespacing is left to the schema source and is not mangled by the linter.

## 4. Transcript formats

### Claude Code JSONL
Each line is one JSON object. We extract entries where `type == "tool_use"` or where the object contains a `tool_calls`/`tool_use`/`name`+`input`/`arguments` structure. Specifically, we look for:

- `name` (str) + `input` (dict)
- `tool_calls` list with `{ name?, function?: { name, arguments } }`
- Legacy: `function_call.name` + `function_call.arguments`

### OpenAI messages
A JSON array of messages. We look for assistant messages with `tool_calls`:

```json
{
  "role": "assistant",
  "tool_calls": [
    {
      "id": "call_123",
      "type": "function",
      "function": { "name": "read_file", "arguments": "{\"file_path\":\"/etc/passwd\"}" }
    }
  ]
}
```

Arguments are JSON strings that are parsed before validation.

## 5. Validation

For each tool call found in the transcript:

1. Look up the schema by exact tool name.
2. If not found → `error: undefined tool`.
3. Parse arguments (string JSON for OpenAI, dict already for Claude Code).
4. Validate against the schema with `jsonschema.validate(instance, schema)`.
5. Map `jsonschema.ValidationError` to a structured violation object.

Severity v1:
- `error` for all validation failures.

## 6. Output formats

### Text

```
/path/to/transcript:42 read_file: missing required argument 'file_path'
/path/to/transcript:67 frobnicate: tool not declared
```

Each violation on its own line with `file:line tool_name: message`.

### JSON

```json
{
  "ok": false,
  "violation_count": 2,
  "violations": [
    {
      "file": "/path/to/transcript",
      "line": 42,
      "tool": "read_file",
      "severity": "error",
      "message": "missing required argument 'file_path'",
      "schema_path": "file_path"
    }
  ]
}
```

## 7. Package layout

```
toolcall-linter/
├── pyproject.toml
├── LICENSE
├── README.md
├── selfcheck.py
├── docs/superpowers/specs/2026-07-21-toolcall-linter-design.md
└── src/toolcall_linter/
    ├── __init__.py
    ├── cli.py
    ├── schema_source.py
    ├── transcript.py
    ├── validator.py
    └── reporter.py
```

Dependencies: `jsonschema` only. Stdlib for the rest.

## 8. selfcheck.py

A single Python script that:

1. Creates a temporary directory.
2. Writes a `tools.json` with two tools: `read_file` and `delete_file`.
3. Writes a Claude Code JSONL transcript containing:
   - a valid `read_file` call,
   - a call to `read_file` missing `file_path`,
   - a call to `read_file` with wrong type for `file_path`,
   - a call to `read_file` with an extra undeclared argument,
   - a call to an undeclared tool `frobnicate`,
   - a call to `delete_file` with an invalid enum value for `confirm`.
4. Runs `python -m toolcall_linter.cli <transcript> --tools <tools.json> --format json`.
5. Asserts exit code is `1` and that each expected violation is reported.

## 9. License

MIT.

## 10. Out of scope (YAGNI)

- Auto-fix or rewrite of transcripts.
- GitHub Action / CI integration.
- Streaming attach to live agent sessions.
- Semantic heuristics ("wrong tool for the job").
- Multiple schema sources in one invocation.
