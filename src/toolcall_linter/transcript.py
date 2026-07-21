"""Parse tool calls from Claude Code JSONL and OpenAI messages transcripts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass(frozen=True)
class ToolCall:
    line: int
    tool: str
    arguments: dict


def parse_transcript(path: Path) -> Iterator[ToolCall]:
    if not path.exists():
        raise FileNotFoundError(f"transcript not found: {path}")
    text = path.read_text(encoding="utf-8")
    first = text.lstrip()[:1]
    if first == "[":
        yield from _parse_openai_array(text)
    else:
        yield from _parse_jsonl(text)


def _parse_jsonl(text: str) -> Iterator[ToolCall]:
    """Claude Code JSONL: each line is a JSON event object."""
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        yield from _extract_calls_from_object(obj, line_no)


def _extract_calls_from_object(obj: Any, line: int) -> Iterator[ToolCall]:
    """Best-effort extraction of tool calls from a single transcript object."""
    if not isinstance(obj, dict):
        return

    # Direct {name, input} shape used by Claude Code tool_use blocks.
    if isinstance(obj.get("name"), str) and isinstance(obj.get("input"), dict):
        yield ToolCall(line=line, tool=obj["name"], arguments=obj["input"])
        return

    # OpenAI assistant tool_calls list.
    for call in _listify(obj.get("tool_calls")):
        name, args = _name_and_args_from_call(call)
        if name:
            yield ToolCall(line=line, tool=name, arguments=args)

    # Legacy function_call field.
    fn = obj.get("function_call")
    if isinstance(fn, dict):
        name, args = _name_and_args_from_call(fn)
        if name:
            yield ToolCall(line=line, tool=name, arguments=args)


def _parse_openai_array(text: str) -> Iterator[ToolCall]:
    messages = json.loads(text)
    if not isinstance(messages, list):
        raise ValueError("OpenAI transcript must be a JSON array of messages")
    for idx, msg in enumerate(messages, start=1):
        if not isinstance(msg, dict):
            continue
        for call in _listify(msg.get("tool_calls")):
            name, args = _name_and_args_from_call(call)
            if name:
                yield ToolCall(line=idx, tool=name, arguments=args)


def _name_and_args_from_call(call: Any) -> tuple[str | None, dict]:
    if not isinstance(call, dict):
        return None, {}
    name: str | None = call.get("name")
    func = call.get("function")
    if not name and isinstance(func, dict):
        name = func.get("name")

    raw_args = call.get("arguments")
    if raw_args is None and isinstance(func, dict):
        raw_args = func.get("arguments")

    args: dict = {}
    if isinstance(raw_args, dict):
        args = raw_args
    elif isinstance(raw_args, str):
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            args = {"__raw__": raw_args}
    return name, args if isinstance(args, dict) else {"__raw__": raw_args}


def _listify(value: Any) -> list:
    if isinstance(value, list):
        return value
    return []
