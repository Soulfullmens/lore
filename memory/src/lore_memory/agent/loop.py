"""The reference ReAct agent.

A thin, framework-free loop that implements the ``Agent`` protocol the
harness drives. It owns retrieval — it calls ``memory.retrieve`` itself —
so the ablation seam threads harness -> agent -> memory via ``ablate_ids``
without the harness reaching inside the loop.

The loop is deliberately minimal (~think/act/observe until finish or step
cap). Everything that makes the project interesting lives in the memory
backend, not here; this agent stays constant so that differences between
runs are attributable to memory, not to a changing controller.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Collection, Sequence

from ..models import AgentStep, Episode, Outcome, OutcomeStatus, RetrievedMemory
from ..protocols import MemoryBackend, Task
from .llm import LLMClient, Message
from .prompts import build_system_prompt
from .tools import ToolRegistry, Tool


class ReActAgent:
    def __init__(
        self,
        llm: LLMClient,
        *,
        tools: Sequence[Tool] | None = None,
        max_steps: int = 12,
        retrieve_k: int = 5,
    ) -> None:
        self._llm = llm
        self._registry = ToolRegistry(tools)
        self._max_steps = max_steps
        self._k = retrieve_k

    def run(
        self,
        task: Task,
        memory: MemoryBackend,
        *,
        seed: int,
        ablate_ids: Collection[str] = (),
    ) -> Episode:
        workspace = tempfile.mkdtemp(prefix=f"lore_{task.id}_")
        try:
            return self._run_in(workspace, task, memory, seed, ablate_ids)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    # ----------------------------------------------------------------- #
    def _run_in(
        self,
        workspace: str,
        task: Task,
        memory: MemoryBackend,
        seed: int,
        ablate_ids: Collection[str],
    ) -> Episode:
        # Task seeds its files into the fresh workspace.
        task.setup(workspace)  # type: ignore[attr-defined]

        # --- read path: retrieve memories (ablation-aware) -------------- #
        retrieved: list[RetrievedMemory] = memory.retrieve(
            task.prompt(), k=self._k, exclude_ids=tuple(ablate_ids)
        )
        system = build_system_prompt(retrieved)

        messages: list[Message] = [
            Message("system", system),
            Message("user", task.prompt()),
        ]

        trajectory: list[AgentStep] = []
        tokens_in = tokens_out = 0
        finished = False

        for step_idx in range(self._max_steps):
            resp = self._llm.complete(
                messages, self._registry.specs(), seed=seed, temperature=0.0
            )
            tokens_in += resp.tokens_in
            tokens_out += resp.tokens_out

            if not resp.tool_calls:
                # Model answered in prose with no action — record and stop.
                trajectory.append(AgentStep(resp.text, "(no action)", "", resp.tokens_in, resp.tokens_out))
                break

            # Append assistant message with its tool calls
            messages.append(
                Message(
                    role="assistant",
                    content=resp.text or "",
                    tool_calls=resp.tool_calls,
                )
            )

            for i, call in enumerate(resp.tool_calls):
                observation = self._registry.dispatch(workspace, call)
                trajectory.append(
                    AgentStep(
                        thought=resp.text,
                        action=f"{call.name}({call.args})",
                        observation=observation,
                        tokens_in=resp.tokens_in,
                        tokens_out=resp.tokens_out,
                    )
                )
                call_id = call.id or f"call_{step_idx}_{i}"
                messages.append(
                    Message(
                        role="tool",
                        content=observation,
                        tool_name=call.name,
                        tool_call_id=call_id,
                    )
                )
                if call.name == ToolRegistry.FINISH:
                    finished = True
            if finished:
                break

        # --- grade deterministically ----------------------------------- #
        try:
            outcome = task.evaluate(workspace)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - grading fault is infra, not agent failure
            outcome = Outcome(OutcomeStatus.ERROR, detail=f"eval raised: {exc}")

        return Episode(
            task_id=task.id,
            task_family=task.family,
            task_description=task.prompt(),
            trajectory=trajectory,
            outcome=outcome,
            seed=seed,
            tokens_used=tokens_in + tokens_out,
            injected_memory_ids=[m.id for m in retrieved],
        )
