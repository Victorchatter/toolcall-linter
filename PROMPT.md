# toolcall-linter — bootstrap session prompt

You are bootstrapping a new open-source project. Follow the full process: `superpowers:brainstorming` → lock design → write spec to `docs/superpowers/specs/YYYY-MM-DD-toolcall-linter-design.md` → commit → `superpowers:writing-plans` (approve) → implement via `superpowers:executing-plans`. Verify with `selfcheck.py` before done.

## Idea (one-liner)
A local linter that cross-checks an agent transcript's tool calls against the declared tool schemas and flags the #1 silent agent failure mode: calls to undefined tools, wrong argument arity, wrong-typed args, missing required args, and unrecognized enum values. Reads a transcript + a tool-schema source (an MCP server's `tools/list`, an OpenAI tools array, or a `tools.json` file) and prints violations.

## Why it doesn't exist
Schema validators exist, but none are wired to real agent transcripts. Agents silently pass garbage args and fail in confusing ways downstream; this catches it at lint time.

## Hard constraints
- Python, `pipx install .`. Fully local/offline, no telemetry. Read-only.
- Two inputs: the transcript (Claude Code JSONL / OpenAI messages) and the tool-schema source. Support at least: (a) a static `tools.json`, (b) querying a live MCP server via `tools/list` over stdio or HTTP. Optional (c) OpenAI `tools` array embedded in a request log.
- Schema validation: JSON-schema based for arg types/required/enum; plus a "tool not declared" check (call to a name absent from the schema set).
- Small and sharp. One CLI: `toolcall-linter <transcript> --tools <source> [--format text|json]`. Exit nonzero if any violation.
- Ponytail: shortest working diff, stdlib + `jsonschema` only, no unrequested abstractions. `# ponytail:` comments on simplifications.
- One `selfcheck.py`: a synthetic transcript + tools.json with one of each violation class; assert the linter reports all of them and exits nonzero.
- License MIT. README with a real before/after example.

## Scope / YAGNI (v1)
Ship: static `tools.json` + live MCP `tools/list` sources, JSON-schema arg validation, undefined-tool detection, text + JSON output. Out: auto-fix, CI GitHub Action (follow-up), streaming attach, semantic "wrong tool for the job" heuristics.

## Inputs to lock during brainstorming
- Whether to use `jsonschema` (recommended, stdlib-adjacent) vs hand-rolled validators.
- How to match a tool call in the transcript to its schema when names collide across servers (recommend `server:tool` keys for MCP).
- Severity levels (recommend error/warn/info).

One of 10 sibling local-first agent-tooling projects. Keep it small and ship it.