"""Run Lore's ReActAgent on Nebius Token Factory with an NVIDIA Nemotron model.

Nebius x NVIDIA Global AI Hackathon — Coding & Agentic Engineering track.

Usage (PowerShell):
    $env:NEBIUS_API_KEY="..."
    $env:LORE_LLM_BASE_URL="https://api.studio.nebius.com/v1/"
    $env:LORE_MODEL="nvidia/llama-3.1-nemotron-ultra-253b-v1"
    python memory/examples/run_nebius_nemotron.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from lore_memory.agent import OpenRouterClient, ReActAgent
from lore_memory.backends import NullMemoryBackend
from lore_memory.eval import Harness, Mode, RunConfig
from lore_memory.tasks import load_tasks

TASKS_ROOT = Path(__file__).resolve().parent.parent / "tasks"


def main() -> None:
    model = os.environ.get("LORE_MODEL")
    if not model:
        print("ERROR: Set LORE_MODEL to the Nemotron model ID on Nebius Token Factory.")
        print("  Example: $env:LORE_MODEL=\"nvidia/llama-3.1-nemotron-ultra-253b-v1\"")
        sys.exit(1)

    base_url = os.environ.get("LORE_LLM_BASE_URL", "https://api.studio.nebius.com/v1/")

    print("=" * 64)
    print("  Lore — Nebius x NVIDIA Global AI Hackathon")
    print("  Coding & Agentic Engineering Track")
    print("=" * 64)
    print(f"  Model      : {model}")
    print(f"  Base URL   : {base_url}")
    print(f"  Running on : Nebius Token Factory")
    print("=" * 64)

    # Load tasks (reuses the same task suite as run_baseline.py)
    tasks = load_tasks(TASKS_ROOT)
    if not tasks:
        raise SystemExit(f"No tasks found under {TASKS_ROOT}")

    print(f"\nLoaded {len(tasks)} tasks across families: {sorted({t.family for t in tasks})}")

    # Build OpenRouterClient pointed at Nebius Token Factory
    llm = OpenRouterClient(model=model, base_url=base_url, max_tokens=4096)
    agent = ReActAgent(llm, max_steps=12)
    harness = Harness(agent, tasks)
    cfg = RunConfig(seeds=(0,))  # single seed for a quick demo

    print("\n--- Running baseline (no memory) ---")
    report = harness.run(baseline_factory=NullMemoryBackend, memory_factory=None, config=cfg)

    base = report.per_condition[Mode.BASELINE]

    print("\n" + "=" * 64)
    print(f"  Model          : {model}")
    print(f"  Infrastructure : Nebius Token Factory")
    print(f"  Success rate   : {base.success}")
    print(f"  Tokens / success: {base.tokens_per_success}")
    print(f"  Scored attempts: {base.n_attempts}")
    print("=" * 64)
    print("Done.")


if __name__ == "__main__":
    main()
