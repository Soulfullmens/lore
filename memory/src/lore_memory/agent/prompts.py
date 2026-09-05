"""Prompt construction.

The system prompt is the single hook where memory influences behaviour:
retrieved lessons are rendered here, ahead of the task. Keeping it in one
small function makes the injection point explicit and easy to ablate —
withhold a memory upstream and it simply never appears in this text.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..models import RetrievedMemory

_BASE = """You are an autonomous coding agent working inside a sandboxed workspace.

Solve the task by inspecting and editing files with the provided tools, then \
running the checks to confirm your fix. Work in small steps: read before you \
write, and run the check command before you finish. Call `finish` only once the \
checks pass.

Available tools: read_file, write_file, list_dir, run_shell, finish."""


def build_system_prompt(memories: Sequence[RetrievedMemory]) -> str:
    """Assemble the system prompt, injecting retrieved memories if any.

    Memories are presented as advisory lessons with their confidence, not
    as commands — the agent must still verify against the checks. This
    matters: Lore's own results showed prescriptive, unverified injection
    can *harm* performance, which is exactly why confidence is surfaced and
    why the checks remain the ground truth.
    """
    if not memories:
        return _BASE

    lines = [
        _BASE,
        "",
        "Relevant lessons from past experience (advisory — verify against the checks):",
    ]
    for m in memories:
        conf = m.metadata.get("confidence")
        tag = f" (confidence {conf:.2f})" if isinstance(conf, (int, float)) else ""
        lines.append(f"- {m.content}{tag}")
    return "\n".join(lines)
