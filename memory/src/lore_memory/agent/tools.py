"""Agent tools, sandboxed to a per-attempt workspace.

Every tool operates inside a single workspace directory and refuses paths
that escape it. The agent runs real code (it must, to solve coding tasks),
so containment + timeouts are the safety floor: one temp dir per attempt,
no path traversal, bounded shell execution, truncated output.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Callable

from .llm import ToolSpec

MAX_OUTPUT_CHARS = 4000
SHELL_TIMEOUT_SEC = 30


def _resolve(workspace: str, path: str) -> str:
    """Resolve ``path`` within ``workspace``; reject escapes."""
    root = os.path.realpath(workspace)
    full = os.path.realpath(os.path.join(root, path))
    if full != root and not full.startswith(root + os.sep):
        raise ValueError(f"path {path!r} escapes the workspace")
    return full


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n...[truncated {len(text) - MAX_OUTPUT_CHARS} chars]"


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., str]

    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.parameters)


def _read_file(workspace: str, path: str) -> str:
    full = _resolve(workspace, path)
    if not os.path.isfile(full):
        return f"ERROR: no such file: {path}"
    with open(full, encoding="utf-8") as fh:
        return _truncate(fh.read())


def _write_file(workspace: str, path: str, content: str) -> str:
    full = _resolve(workspace, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)
    return f"wrote {len(content)} chars to {path}"


def _list_dir(workspace: str, path: str = ".") -> str:
    full = _resolve(workspace, path)
    if not os.path.isdir(full):
        return f"ERROR: not a directory: {path}"
    entries = sorted(os.listdir(full))
    return "\n".join(entries) if entries else "(empty)"


def _run_shell(workspace: str, command: str) -> str:
    try:
        proc = subprocess.run(
            command,
            cwd=workspace,
            shell=True,
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: command timed out after {SHELL_TIMEOUT_SEC}s"
    out = f"exit={proc.returncode}\n--- stdout ---\n{proc.stdout}"
    if proc.stderr.strip():
        out += f"\n--- stderr ---\n{proc.stderr}"
    return _truncate(out)


def default_tools() -> list[Tool]:
    """The Phase-0 tool set. ``finish`` is handled by the loop, not here."""
    return [
        Tool(
            "read_file",
            "Read a UTF-8 text file from the workspace.",
            {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "path relative to workspace"}},
                "required": ["path"],
            },
            _read_file,
        ),
        Tool(
            "write_file",
            "Create or overwrite a file with the given full contents.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string", "description": "the complete new file contents"},
                },
                "required": ["path", "content"],
            },
            _write_file,
        ),
        Tool(
            "list_dir",
            "List entries in a workspace directory.",
            {
                "type": "object",
                "properties": {"path": {"type": "string", "default": "."}},
            },
            _list_dir,
        ),
        Tool(
            "run_shell",
            "Run a shell command in the workspace (30s timeout). Use to run tests.",
            {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            _run_shell,
        ),
    ]


class ToolRegistry:
    """Holds tools, exposes their specs to the LLM, and dispatches calls."""

    FINISH = "finish"

    def __init__(self, tools: Sequence[Tool] | None = None) -> None:
        self._tools = {t.name: t for t in (tools or default_tools())}

    def specs(self) -> list[ToolSpec]:
        specs = [t.spec() for t in self._tools.values()]
        specs.append(
            ToolSpec(
                self.FINISH,
                "Call when the task is complete. Optionally summarise what you did.",
                {"type": "object", "properties": {"summary": {"type": "string"}}},
            )
        )
        return specs

    def dispatch(self, workspace: str, call) -> str:
        if call.name == self.FINISH:
            return call.args.get("summary", "done")
        tool = self._tools.get(call.name)
        if tool is None:
            return f"ERROR: unknown tool {call.name!r}"
        try:
            return tool.fn(workspace, **call.args)
        except TypeError as exc:
            return f"ERROR: bad arguments for {call.name}: {exc}"
        except Exception as exc:  # noqa: BLE001 - surfaced to the agent as an observation
            return f"ERROR: {type(exc).__name__}: {exc}"
