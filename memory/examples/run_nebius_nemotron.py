"""Run Lore's ReActAgent on Nebius Token Factory with an NVIDIA Nemotron model.

Nebius x NVIDIA Global AI Hackathon — Coding & Agentic Engineering track.

Demonstrates Nemotron powering a real coding agent that:
  1. Reads buggy Python code via tool calls
  2. Reasons about the root cause
  3. Generates and applies fixes
  4. Runs test suites to verify
  5. Optionally uses Lore's verified procedural knowledge (lessons) for harder bugs

Usage (PowerShell):
    $env:NEBIUS_API_KEY="..."
    $env:LORE_LLM_BASE_URL="https://api.studio.nebius.com/v1/"
    $env:LORE_MODEL="<Nemotron model ID from Nebius catalog>"
    python memory/examples/run_nebius_nemotron.py
    python memory/examples/run_nebius_nemotron.py --with-memory   # adds lesson injection
    python memory/examples/run_nebius_nemotron.py --seeds 5       # multi-seed evaluation
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from lore_memory.agent import OpenRouterClient, ReActAgent
from lore_memory.backends import NullMemoryBackend
from lore_memory.eval import Harness, Mode, RunConfig
from lore_memory.tasks import load_tasks

TASKS_ROOT = Path(__file__).resolve().parent.parent / "tasks"

BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║          Lore — Coding Agent on NVIDIA Nemotron              ║
║       Nebius x NVIDIA Global AI Hackathon 2026               ║
║       Coding & Agentic Engineering Track                     ║
╚══════════════════════════════════════════════════════════════╝
"""


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run Lore's coding agent with NVIDIA Nemotron on Nebius Token Factory"
    )
    ap.add_argument(
        "--seeds", type=int, default=1,
        help="number of seeds for evaluation (1 = quick demo, 5+ = statistical eval)"
    )
    ap.add_argument(
        "--family", default=None,
        help="filter tasks by family name (e.g. 'acme-stream', 'retry-decorator')"
    )
    ap.add_argument(
        "--task", default=None,
        help="filter tasks by task id"
    )
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument(
        "--with-memory", action="store_true", default=False,
        help="enable Lore lesson injection (Phase 1 episodic memory) alongside baseline"
    )
    args = ap.parse_args()

    # ── Validate env vars ────────────────────────────────────────────
    model = os.environ.get("LORE_MODEL")
    if not model:
        print("ERROR: Set LORE_MODEL to the Nemotron model ID on Nebius Token Factory.")
        print('  Example: $env:LORE_MODEL="<Nemotron model ID from Nebius catalog>"')
        sys.exit(1)

    base_url = os.environ.get("LORE_LLM_BASE_URL", "https://api.studio.nebius.com/v1/")

    api_key = os.environ.get("NEBIUS_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: Set NEBIUS_API_KEY to your Nebius Token Factory API key.")
        sys.exit(1)

    # ── Banner ───────────────────────────────────────────────────────
    print(BANNER)
    print(f"  Model          : {model}")
    print(f"  Base URL       : {base_url}")
    print(f"  Infrastructure : Nebius Token Factory")
    print(f"  Seeds          : {args.seeds}")
    print(f"  Memory         : {'ON (lesson injection)' if args.with_memory else 'OFF (baseline)'}")
    print()

    # ── Load tasks ───────────────────────────────────────────────────
    tasks = load_tasks(TASKS_ROOT)
    if not tasks:
        raise SystemExit(f"No tasks found under {TASKS_ROOT}")

    if args.family:
        tasks = [t for t in tasks if t.family == args.family or t.is_control]
    if args.task:
        tasks = [t for t in tasks if t.id == args.task or t.is_control]

    families = sorted({t.family for t in tasks})
    print(f"  Loaded {len(tasks)} tasks across {len(families)} families: {families}")

    # ── Build LLM client pointed at Nebius Token Factory ─────────────
    llm = OpenRouterClient(model=model, base_url=base_url, max_tokens=args.max_tokens)
    agent = ReActAgent(llm, max_steps=args.max_steps)
    harness = Harness(agent, tasks)
    cfg = RunConfig(seeds=tuple(range(args.seeds)))

    memory_factory = None
    if args.with_memory:
        from lore_memory.store import EpisodicMemoryBackend, HashEmbedder
        def memory_factory():
            return EpisodicMemoryBackend(embedder=HashEmbedder(dim=256))

    # ── Run ──────────────────────────────────────────────────────────
    t0 = time.perf_counter()

    print("\n" + "─" * 64)
    if args.with_memory:
        print("  Phase: BASELINE (no memory) + MEMORY (Lore lessons injected)")
    else:
        print("  Phase: BASELINE (no memory)")
    print("─" * 64 + "\n")

    report = harness.run(
        baseline_factory=NullMemoryBackend,
        memory_factory=memory_factory,
        config=cfg,
    )
    elapsed = time.perf_counter() - t0

    # ── Results ──────────────────────────────────────────────────────
    base = report.per_condition.get(Mode.BASELINE)
    mem = report.per_condition.get(Mode.MEMORY)

    print("\n" + "═" * 64)
    print("  RESULTS — NVIDIA Nemotron on Nebius Token Factory")
    print("═" * 64)
    print(f"  Model           : {model}")
    print(f"  Infrastructure  : Nebius Token Factory")
    print(f"  Wall-clock time : {elapsed:.1f}s")
    print()

    if base:
        print(f"  BASELINE Success Rate   : {base.success}")
        print(f"  BASELINE Tokens/Success : {base.tokens_per_success}")
        print(f"  BASELINE Scored Attempts: {base.n_attempts}")

    if mem:
        print(f"\n  MEMORY Success Rate     : {mem.success}")
        print(f"  MEMORY Tokens/Success   : {mem.tokens_per_success}")
        print(f"  MEMORY Scored Attempts  : {mem.n_attempts}")

        lift = report.improvement()
        if lift is not None:
            print(f"\n  Lift (Memory − Baseline): {lift:+.3f}")

    # ── Per-task breakdown ───────────────────────────────────────────
    by_task: dict[str, list[bool]] = defaultdict(list)
    for r in report.records:
        if r.mode == Mode.BASELINE and r.countable:
            by_task[r.task_id].append(r.success)

    print("\n  ── Per-Task Breakdown (Baseline) ──")
    for tid, results in sorted(by_task.items()):
        p = sum(results)
        t = len(results)
        rate = p / t if t else 0.0
        status = "✓" if rate == 1.0 else ("◐" if rate > 0 else "✗")
        print(f"    {status} {tid:30s}: {p}/{t} ({rate:.0%})")

    print("\n" + "═" * 64)
    print("  Powered by NVIDIA Nemotron · Served on Nebius Token Factory")
    print("═" * 64)


if __name__ == "__main__":
    main()
