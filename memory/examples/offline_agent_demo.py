"""Offline proof that the real agent loop works — no API key needed.

This runs the *actual* ReActAgent, with the *actual* tools, against the
*actual* safe_gather task, graded by the *actual* check.py subprocess.
Only the LLM is swapped: a ScriptedClient replays the exact tool-call
sequence a competent agent would produce. If this run reports SUCCESS, the
loop, the sandbox, the tools, and the deterministic grader are all real —
and swapping in GeminiClient changes nothing but the source of the actions.

Run:  python -m examples.offline_agent_demo
"""

from __future__ import annotations

from pathlib import Path

from lore_memory.agent import ReActAgent, ScriptedClient
from lore_memory.agent.llm import LLMResponse, ToolCall
from lore_memory.backends import NullMemoryBackend
from lore_memory.models import OutcomeStatus
from lore_memory.tasks import load_task

TASK_DIR = Path(__file__).resolve().parent.parent / "tasks" / "python_async" / "safe_gather"

FIXED_SOLUTION = '''"""Fixed solution — gather with return_exceptions captures failures."""
import asyncio


async def safe_gather(coros):
    return await asyncio.gather(*coros, return_exceptions=True)
'''

# The scripted "reasoning": look at the file, apply the fix, run the check,
# then finish. Exactly what a capable agent would do.
SCRIPT = [
    LLMResponse(
        text="Let me read the current solution.",
        tool_calls=[ToolCall("read_file", {"path": "solution.py"})],
        tokens_in=180, tokens_out=20,
    ),
    LLMResponse(
        text="It calls gather without return_exceptions. I'll add it.",
        tool_calls=[ToolCall("write_file", {"path": "solution.py", "content": FIXED_SOLUTION})],
        tokens_in=210, tokens_out=60,
    ),
    LLMResponse(
        text="Now run the check.",
        tool_calls=[ToolCall("run_shell", {"command": "python check.py"})],
        tokens_in=150, tokens_out=15,
    ),
    LLMResponse(
        text="Checks pass.",
        tool_calls=[ToolCall("finish", {"summary": "added return_exceptions=True"})],
        tokens_in=140, tokens_out=10,
    ),
]


def main() -> None:
    task = load_task(TASK_DIR)
    agent = ReActAgent(ScriptedClient(SCRIPT))
    memory = NullMemoryBackend()
    memory.setup()

    episode = agent.run(task, memory, seed=0)

    print("=== Real loop, real task, real grader (scripted LLM) ===")
    print(f"task            : {task.id}  (family={task.family})")
    print(f"steps taken     : {len(episode.trajectory)}")
    print(f"tokens used     : {episode.tokens_used}")
    print(f"outcome         : {episode.outcome.status.value}")
    if episode.outcome.detail:
        print(f"detail          : {episode.outcome.detail.strip()[:120]}")
    print(f"injected memory : {episode.injected_memory_ids}  (empty: memory-off baseline)")
    print()
    for i, step in enumerate(episode.trajectory, 1):
        obs = step.observation.replace("\n", " ")[:70]
        print(f"  step {i}: {step.action[:48]:48}  -> {obs}")
    print()
    ok = episode.outcome.status is OutcomeStatus.SUCCESS
    print("RESULT:", "PASS -- the loop genuinely solved the task" if ok else "FAIL")

    if not ok:
        # Also show full detail on failure for debugging.
        print(f"\nFull outcome detail:\n{episode.outcome.detail}")


if __name__ == "__main__":
    main()
