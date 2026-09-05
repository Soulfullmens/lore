# lore-memory — Phase 0 foundation

Framework-agnostic, compounding agent-memory engine. This is the Phase 0
skeleton: the **contracts** everything hangs off, plus a **measurement
harness** with the advanced seams wired in from the first commit.

There is deliberately no intelligence yet. Phase 0's job is to produce a
trustworthy baseline — the flat success line every later phase must beat.

## What's here

| File | Role |
|------|------|
| `lore_memory/models.py` | Shared data models: `Episode`, `Lesson`, `Skill`, `Outcome`, `RetrievedMemory`, `CreditUpdate`. |
| `lore_memory/protocols.py` | The contracts: `MemoryBackend`, `StorageBackend`, `EmbeddingProvider`, `Agent`, `Task`, `Tracer`. No framework, driver, or LLM SDK imported. |
| `lore_memory/backends/null.py` | `NullMemoryBackend` — the memory-off baseline, a real impl of the protocol so baseline and memory runs share one code path. |
| `lore_memory/eval/harness.py` | The measurement harness: multi-seed, ablation, contamination control. |
| `lore_memory/eval/stats.py` | Bootstrap CIs + Welch's t — every metric ships with error bars. |
| `examples/phase0_smoke.py` | Runs offline, no API keys. Proves the harness + seams work end to end. |

## The three seams (built now, filled in later)

1. **Causal credit via ablation** — `MemoryBackend.retrieve(..., exclude_ids=)`
   lets the harness withhold one injected memory and re-run the *same seed*,
   measuring the success delta. That is a causal signal, not an LLM-judge
   guess — the direct answer to the Verification column everyone scores 1/5.
2. **Multi-seed rigour** — `Agent.run(..., seed=)` + bootstrap CIs. No
   single-run screenshots; results are `mean [lo, hi]`.
3. **Contamination control** — `Task.is_control` marks no-memory-possible
   tasks. If memory-on beats memory-off *there*, gains are an artefact, and
   the report flags it.

Observability is a fourth seam: every backend accepts a `Tracer`, default
no-op, so OpenTelemetry drops in without touching the engine.

## Run the baseline

```bash
cd memory
pip install -e .
python -m examples.phase0_smoke
```

You'll get a success-rate estimate with a confidence interval, a
tokens/success cost figure, a contamination check, and (at baseline) zero
ablation records — because there's no memory to withhold yet.

## Design rules that matter

- **The engine never imports an agent framework.** Frameworks are adapters
  (Phase 6), not foundations.
- **Baseline and memory are two impls of one protocol.** The only honest
  way to attribute a difference to memory.
- **`ERROR` outcomes are excluded from success rates and never memorised.**
  Infra flakiness must not pollute the corpus or the graphs.
- **Tasks come in families.** Relatedness is what makes learning
  measurable — random tasks give no transfer signal.

## Next (Phase 1)

Add `store/episode_store.py` (SQLite + sqlite-vec behind `StorageBackend`)
and a real retrieval-augmented agent that populates `injected_memory_ids`.
The harness already supports it — pass a real `memory_factory` to
`Harness.run` and the lift, cost delta, and ablation deltas fill in.
