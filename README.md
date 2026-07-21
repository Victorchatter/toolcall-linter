# toolcall-linter

A local, offline CLI linter that cross-checks an agent transcript's tool calls against declared tool schemas.

It catches the most common silent agent failure modes:

- calls to an undeclared tool
- missing required arguments
- wrong argument types
- extra / unexpected arguments
- unrecognized enum values

## Install

```bash
pipx install .
```

## Usage

```bash
# static tools.json
toolcall-linter transcript.jsonl --tools tools.json

# live MCP server over stdio
toolcall-linter transcript.jsonl --tools "mcp-stdio:python -m my_mcp_server"

# live MCP server over HTTP
toolcall-linter transcript.jsonl --tools mcp-http:http://localhost:3000

# JSON output
toolcall-linter transcript.jsonl --tools tools.json --format json
```

## Before / after

Given this `tools.json`:

```json
{
  "tools": [
    {
      "name": "read_file",
      "inputSchema": {
        "type": "object",
        "properties": {
          "file_path": { "type": "string" }
        },
        "required": ["file_path"],
        "additionalProperties": false
      }
    }
  ]
}
```

And this transcript line:

```json
{"type": "tool_use", "name": "read_file", "input": {"path": "/etc/passwd"}}
```

Before, the agent would silently fail downstream. After:

```text
transcript.jsonl:1 read_file: 'file_path' is a required property
```

Exit code is `1` when any violation is found, `2` for CLI/config errors, and `0` when clean.

## Supported transcript formats

- Claude Code JSONL (`name` + `input`, or `tool_calls` arrays)
- OpenAI messages JSON array (`assistant` messages with `tool_calls.function.arguments`)

## Supported schema sources

- Static `tools.json`
- MCP `tools/list` over stdio (`mcp-stdio:<command>`)
- MCP `tools/list` over HTTP (`mcp-http:<url>`)

## Development

```bash
python selfcheck.py
```

## License

MIT.
