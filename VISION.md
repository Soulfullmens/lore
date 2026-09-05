# Lore — a Verified Experience Commons for Agents

## Thesis

Retrieval is not learning. Today's agent-memory tools store and recall text, but
they don't verify what actually worked, don't forget what didn't, and don't let
one agent build on another's proven experience. Lore is a **commons**: agents
contribute episodes of real work, the useful ones are distilled and verified,
and any agent can draw on the whole pool. Competence compounds across agents,
not just within one.

This document is a **roadmap**, not a status report. Each section marks what is
built today versus what is proposed. Nothing below is claimed as working unless
it says "Built."

---

## The two-layer model (and where Lore stops)

A useful agent that acts in the world has two very different needs:

- **Control** — moving, calling, actuating. Millisecond-latency, raw commands.
  For physical devices this is the layer Anthropic's Model Hardware Standard
  (MHS), ROS, and device drivers address. It is a real-time systems problem.
- **Memory** — knowing what worked before and reusing it. Seconds-to-minutes
  latency, task-level abstractions ("this strategy solved that class of bug").

**Lore is the memory layer, for any agent, and only the memory layer.** It does
not issue motor commands, coordinate devices in real time, or replace a
controller. When people picture "robots sharing a nervous system," the nervous
system is the control layer; Lore is the shared *long-term memory* those agents
read from and write to. Keeping this boundary sharp is what keeps the project
tractable: a robot agent and a coding agent record experience through the
*identical* Lore path, and Lore never needs to know which is which.

---

## What is built today

**Phase 0 — Foundation & measurement (Built).** Framework-agnostic protocols
(`MemoryBackend`, `StorageBackend`, `EmbeddingProvider`, `Agent`, `Task`,
`Tracer`); a ReAct agent loop with sandboxed tools; a `NullMemoryBackend`
memory-off baseline; and an evaluation harness with multi-seed bootstrap
confidence intervals, leave-one-out causal ablation, and a contamination guard.
Dual providers (OpenRouter, Gemini). The agent loop is held constant across
conditions so any measured difference is attributable to memory.

**Phase 1 — Episodic memory (Built).** `SqliteEpisodeStore` (persistent SQLite;
exact Python cosine search by default, with `sqlite-vec` as an optional
accelerator behind the same interface); `HashEmbedder` (offline, deterministic)
and `GeminiEmbedder`; and `EpisodicMemoryBackend`, the memory-on backend that
implements the same protocol as the null baseline.

**Commons layer (Built).** Every episode carries provenance — `agent_id` and
`source` (which agent produced it, and what kind of agent). Retrieval takes a
scope:

- `scope="shared"` — draw from the whole commons; learn from every agent.
- `scope="self"` — isolated; only this agent's own history (the single-agent
  baseline).
- `scope=[agent_ids]` — a chosen, trusted subset.

Offline demos confirm cross-agent transfer (an agent with no history of its own
retrieves a peer's verified success), self-scope isolation, and trusted-subset
filtering. This is the substrate the rest of the vision sits on: `source` is the
single seam where a physical-agent domain would later plug in, unchanged.

**Measurement status (honest).** On the current task suite, a capable model
(gpt-4o-mini) solves every task cold (100% baseline), so there is no headroom to
measure memory lift yet. The engine is sound; the benchmark needs tasks the
model gets *wrong* cold before any lift number is meaningful. See "Change 1."

---

## The changes needed to reach the vision

Ordered. Each is a concrete change, not a slogan. Earlier changes gate later
ones — a positive learning signal must exist before sharing or physical
extension means anything.

### Change 1 — Tasks with real headroom (the current blocker)

A lift experiment is only meaningful on tasks the model fails without help.
Because a capable model already knows common idioms, headroom must come from
knowledge it cannot have: post-cutoff or obscure APIs, or project-specific
conventions. **Change:** build a task family the target model fails cold
(screen candidates with the baseline; keep only sub-100% tasks), then measure
memory-on vs memory-off on those. Win condition to pre-register: treatment
success beats the baseline CI upper bound *and* ablation flags the seed lesson
as causally helpful.

### Change 2 — Consolidation (episodes → lessons)

Today the semantic layer is stubbed. **Change:** an offline "sleep" pass that
clusters episodes, LLM-extracts compact lessons, and dedups them — so the
context injected at run time is a small distilled lesson, not raw trajectories.
This is what moves Lore past "vector-DB wrapper" and is the largest single lift
on token efficiency.

### Change 3 — Verification & confidence (the core edge)

**Change:** each lesson carries `confidence` plus `times_applied` / `times_helped`,
updated by post-task credit assignment (leave-one-out ablation as ground truth,
not an LLM guessing). Retrieval then weights by proven utility. This is the
capability no existing memory tool has, and it's the reason a *commons* is safe:
you share what's verified, not what's merely stored.

### Change 4 — Value-based forgetting

**Change:** retention = f(recency, frequency, verified-utility); prune the bottom
percentile. This keeps the store small and cheap as episodes accumulate — the
"stays lean" story — and prevents the commons from degrading as low-value or
stale memories pile up.

### Change 5 — Trust & safety for a shared commons

Sharing across agents introduces risks a single-agent store doesn't have: a bad
or poisoned memory could propagate. The provenance and scope primitives are in
place; the *policy* on top of them is not. **Change:** verification-gated
sharing (only lessons above a confidence threshold enter `shared` scope),
per-source trust levels, and a quarantine path for unverified contributions.
This is the prerequisite for ever trusting memory from an agent you didn't run
yourself.

### Change 6 — Procedural skills & hybrid retrieval

**Change:** a Voyager-style skill library ("when X, do Y") on top of lessons, and
retrieval that blends relevance × confidence × recency, cheapest-sufficient
layer first. This is the "1.0" of the memory engine.

### Change 7 (north star) — A physical-agent domain

Only after Changes 1–6 produce a real, shared, verified learning signal on
software tasks does a physical extension make sense. **Change:** a new task
`source` (e.g. `robot-arm-agent`) and a domain whose "grader" is a task outcome
in a simulated or real cell. The control itself (MHS/ROS drivers) is out of
scope for Lore and integrated separately; Lore's job is unchanged — store the
verified experience of what worked and share it across the fleet. This is a
framing to build *toward*, not to start now: it depends on hardware, a control
layer, and MHS access (currently a closed research preview), none of which
belong on the critical path today.

---

## Non-goals

Lore does **not**: control devices or issue motor commands; provide real-time
coordination; act as a controller, driver, or MHS/ROS replacement; or store
memory it cannot attribute and (eventually) verify. It is the shared, verified
memory layer — and only that.

---

## Honest ordering

Phases 0–1 and the commons layer are a strong portfolio piece on their own.
Changes 1–4 are the differentiators. Changes 5–6 are the product. Change 7 is
the north star. The fastest way to *lose* the project is to jump to Change 7
before Change 1 has produced a single real lift number — build the evidence in
order, and the physical story becomes credible instead of speculative.
