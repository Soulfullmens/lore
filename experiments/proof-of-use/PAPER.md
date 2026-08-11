# The Limits of In-Context Procedural Knowledge Injection for AI Coding Agents: An Empirical Pilot

**Author:** Soulfullmens & Antigravity  
**Date:** August 2026  
**Target System:** Lore — A Verified Experience Commons for AI  
**Model Tested:** `gemini-3.1-flash-lite` (Temperature = 0.0)  
**Protocol:** Pre-registered in `PROTOCOL.md` (Git commit `403e5d3`)

---

## Abstract

We present an empirical pilot study evaluating whether injecting verified, executable procedural knowledge ("lessons") into an AI coding agent's context window improves task completion speed and success rate during bug resolution. Using a pre-registered protocol, a dual-verification containerized test harness, and 8 exploratory gotcha scenarios spanning Python standard library async behaviors (`asyncio`), Pydantic v2 core/recent APIs, and the Model Context Protocol (`FastMCP`), we measure control performance (symptom + code only) versus treatment performance (symptom + code + verified lesson). 

For the tested model (`gemini-3.1-flash-lite`), our primary finding is a **100% (8/8) cold solve rate** on unassisted control runs across all 8 tested gotcha scenarios (whether via training set memorization or general parametric reasoning, which this study does not differentiate). Consequently, in-context procedural knowledge injection yielded **0% positive performance lift** in this trial suite. Furthermore, we demonstrate that prescriptively worded lessons can introduce **negative performance lift** by overriding valid, context-sensitive model defaults with rigid "best practices." 

**Key Limitation:** Because all 8 exploratory gotcha scenarios were solved cold by the model without assistance, we did not observe a baseline unassisted failure. Therefore, whether in-context injection provides positive 0→1 lift for genuinely un-memorized, private, or post-cutoff gotchas remains an open research question. We discuss the architectural implications for experience registries and knowledge injection systems.

---

## 1. Introduction & Hypothesis

AI coding agents frequently encounter recurring gotchas: subtle framework behaviors, version-specific API shifts, and resource leak traps. The founding premise of *Lore* was that creating a global, executable, container-verified registry of procedural knowledge (with attached evals) would allow agents to retrieve verified lessons at inference time and avoid known failure modes.

### Pre-Registered Hypotheses (PROTOCOL.md §3)
- **Primary Metric:** Turns-to-correct-fix (capped at 6 turns; grade determined by mechanical containerized judge).
- **H1 (Treatment Lift):** Treatment condition (with lesson) solves tasks in fewer turns and at higher rates than control.
- **H0 (Null Hypothesis):** Lesson injection provides no statistically observable difference in solve rate or turns.
- **Disappointment Criterion (Pre-Committed):** If control solves tasks in $\le 2$ turns without assistance, the model already possesses internalized parametric memory or reasoning capabilities for the gotcha, rendering in-context injection redundant.

---

## 2. Experimental Design & Methodology

### 2.1 Decoupled Dual-Verification Harness
To eliminate evaluation bias, we implemented a decoupled harness architecture:
1. **Agent View (`_buggy.py`):** The model receives the raw symptom and realistic, natural code with all giveaway comments and explicit test assertions stripped.
2. **Behavioral Probe (`_probe.py`):** An unseen test harness imports the candidate module and evaluates runtime behavior (e.g. wall-clock latency, stream closure, event log state).
3. **Dual-Check Judge (`_judge.py`):** Evaluates (A) whether the candidate passes positive runtime behavioral assertions AND (B) confirms that the untouched original buggy code fails (preventing false positives from hardware concurrency variances or invalid tests).

### 2.2 Temperature & Model Locking
All trials were executed at `temperature=0.0` using `gemini-3.1-flash-lite` to ensure deterministic execution and isolate lesson presence as the single independent variable.

---

## 3. Empirical Results

### 3.1 Pre-Registered Pilot Study (18 Trials)

| Bug ID | Domain / Gotcha | Control Solved | Treatment Solved | Result |
| :--- | :--- | :---: | :---: | :--- |
| `0002` | `asyncio.gather` detached sibling side-effects | **3 / 3** (turn 1) | **0 / 3** (turn 6) | **Negative Lift (Harm)** |
| `0005` | Async generator `aclose()` cleanup deferral | **3 / 3** (turn 1) | **3 / 3** (turn 1) | **Null (Redundant)** |
| `0006` | Default `run_in_executor` pool starvation | 0 / 3 | 0 / 3 | **Instrument Hardware Check** |

*Note on Bug 0006:* Host machine CPU thread pool capacity (`min(32, cpu_count+4)`) prevented 8 background jobs from saturating the default pool. The dual-check judge correctly detected `probe invalid: original buggy file not starved` and rejected all 6 trials, preventing false positive grading.

### 3.2 Extended Probe Suite (5 Additional Scenarios)

| Scenario | Domain / Gotcha | Control Result | Outcome |
| :--- | :--- | :---: | :--- |
| `probe 1` | `asyncio.subprocess` 1MB pipe buffer deadlock | **1 / 1** (turn 1) | **Null (Redundant)** — Supplied `proc.communicate()` cold |
| `probe 2` | Pydantic v2 `field_validator` on default values | **1 / 1** (turn 1) | **Null (Redundant)** — Supplied `@model_validator` cold |
| `probe 3` | Python 3.13 `asyncio.Queue.shutdown()` & `QueueShutDown` | **1 / 1** (turn 1) | **Null (Redundant)** — Supplied `asyncio.QueueShutDown` cold |
| `probe 4` | Pydantic `ConfigDict(defer_build=True)` initialization | **1 / 1** (turn 1) | **Null (Redundant)** — Supplied `model_rebuild()` cold |
| `probe 5` | FastMCP `Context` dependency injection syntax | **1 / 1** (turn 1) | **Null (Redundant)** — Supplied `ctx: Context` parameter cold |

---

## 4. Key Findings & Discussion

### 4.1 Finding 1: High Unassisted Baseline Capability
Across 8 exploratory scenarios spanning core standard libraries, framework gotchas, Python 3.13 features, and FastMCP SDK patterns, `gemini-3.1-flash-lite` solved **8 out of 8 (100%)** problems on Turn 1 without assistance (whether via training set memorization or general parametric reasoning, which this study does not differentiate). For these scenarios, the tested model solved the problems cold, rendering in-context procedural knowledge injection redundant.

### 4.2 Finding 2: Over-Prescriptive Lessons Cause Negative Performance Lift
In Bug `0002` (`asyncio.gather`), control solved 3/3 in 1 turn by supplying `return_exceptions=True` (allowing all tasks to complete and return results). In treatment, injecting a lesson that prescriptively emphasized `TaskGroup` as a modern "best practice" caused the model to replace `gather` with `TaskGroup`. Because `TaskGroup` cancels sibling tasks upon the first failure, non-failing sibling account transactions were cancelled and omitted from the final reconciliation dictionary, causing **100% of treatment runs to fail**.

> **Takeaway:** Prescriptive procedural knowledge that advocates a "best practice" without explicit symptom-conditional boundaries risks overriding correct, context-sensitive model defaults.

---

## 5. Scope, Limitations & Strategic Recommendations

### 5.1 Study Limitations
1. **Single Model Evaluation:** Results are bounded to `gemini-3.1-flash-lite` at `temperature=0.0`. Other model architectures or parameter sizes may exhibit different baseline knowledge profiles.
2. **Exploratory Pilot Scope:** 8 hand-selected gotcha scenarios represent an exploratory pilot suite rather than an exhaustive benchmark.
3. **Non-Differentiated Baseline Knowledge:** This study measures unassisted solve rate but does not differentiate whether baseline success stems from memorized training data or real-time reasoning.
4. **Untested Cold-Failure Regime:** Because all 8 scenarios were solved unassisted by the model, we did not observe a baseline cold failure. Thus, the degree of lift provided by lesson injection on genuinely un-memorized, private, or post-cutoff gotchas remains unmeasured in this study.

### 5.2 Evidence-Grounded Suggestions for Knowledge Registries
1. **Consider Scoping In-Context Injection to Un-Memorizable Boundaries:** Our findings suggest that experience registries may benefit from avoiding standard library or broadly documented framework gotchas, focusing instead on:
   - Private / enterprise codebase patterns.
   - Fast-evolving, un-memorized API shifts occurring post-model training cutoff.
   - Non-deterministic environment / C-extension gotchas.
2. **Investigate Symptom-Conditional Scoping:** The single negative-lift case observed (`0002`) suggests that procedural knowledge should be formatted conditionally ("Use X only when condition Y is met; avoid X when Z") to prevent overriding context-sensitive model defaults on edge cases.

---

## Appendix: Reproducibility
All prompts, dual-verification judges, and raw JSON trial transcripts are archived in `experiments/proof-of-use/` in the `Soulfullmens/lore` repository.

---

## Appendix: Reproducibility
All prompts, dual-verification judges, and raw JSON trial transcripts are archived in `experiments/proof-of-use/` in the `Soulfullmens/lore` repository.

