"""Load tool schemas from static files or live MCP servers."""

from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any


def load_schema_source(source: str) -> dict[str, dict]:
    """Resolve a --tools source into a mapping of tool_name -> input schema."""
    if source.startswith("mcp-stdio:"):
        return _load_mcp_stdio(source.removeprefix("mcp-stdio:"))
    if source.startswith("mcp-http:"):
        return _load_mcp_http(source.removeprefix("mcp-http:"))
    # ponytail: treat anything else as a local JSON file; no URI scheme zoo in v1.
    return _load_static(Path(source))


def _load_static(path: Path) -> dict[str, dict]:
    if not path.exists():
        raise FileNotFoundError(f"tools file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return _extract_schemas(data)


def _extract_schemas(data: Any) -> dict[str, dict]:
    """Accept either a JSON array of tools or an object with a 'tools' key."""
    tools: list[dict]
    if isinstance(data, list):
        tools = data
    elif isinstance(data, dict) and "tools" in data:
        tools = data["tools"]
    elif isinstance(data, dict) and "result" in data:
        # Raw MCP tools/list response.
        tools = data["result"].get("tools", []) if isinstance(data["result"], dict) else []
    else:
        raise ValueError("schema source must be a tools array or contain a 'tools' key")

    schemas: dict[str, dict] = {}
    for tool in tools:
        name = tool.get("name")
        if not name:
            continue
        schemas[name] = tool.get("inputSchema", tool.get("parameters", {}))
    return schemas


def _load_mcp_stdio(command: str) -> dict[str, dict]:
    """Spawn an MCP server and request tools/list over stdio."""
    # ponytail: simple shell split via shlex; MCP server is expected to speak JSON-RPC.
    import shlex

    args = shlex.split(command)
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    proc = subprocess.run(
        args,
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"MCP stdio server exited {proc.returncode}: {proc.stderr}")
    # Read the first JSON-RPC line from stdout.
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "result" in response:
            return _extract_schemas(response)
    raise RuntimeError("no tools/list response from MCP stdio server")


def _load_mcp_http(url: str) -> dict[str, dict]:
    """Query an MCP server's tools/list endpoint over HTTP."""
    # ponytail: unauthenticated GET; auth and SSE streaming are out of scope for v1.
    req = urllib.request.Request(
        url if re.search(r"/tools/list/?$", url) else f"{url.rstrip('/')}/tools/list",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return _extract_schemas(data)
