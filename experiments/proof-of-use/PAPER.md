# The Limits of In-Context Procedural Knowledge Injection for AI Coding Agents: A Pre-Registered Pilot

**Project:** Lore — A Verified Experience Commons for AI Agents  
**Date:** August 2026  
**Model tested:** `gemini-3.1-flash-lite` (temperature = 0.0)  
**Protocol:** Pre-registered in `PROTOCOL.md` §3, locked at commit `403e5d3` **before any trial was run**.

---

## Abstract

We report a small, pre-registered pilot evaluating whether injecting verified, executable procedural knowledge ("lessons") into an AI coding agent's context improves bug-fixing success and speed. Using a locked protocol and a decoupled, containerized dual-verification harness, we ran **18 trials** (3 bugs × 2 conditions × 3 trials) on Python `asyncio` gotchas, comparing a control condition (symptom + code) against a treatment condition (symptom + code + verified lesson).

For `gemini-3.1-flash-lite`, control solved all three bugs on the first turn in every trial (**9/9**). Treatment solved **6/9** with a higher mean turn count (**2.67 vs 1.00**): the lesson was neutral on two bugs and actively harmful on one, where a prescriptively worded "best practice" lesson steered the model away from a correct, context-appropriate default. Injection therefore produced **no positive lift and measurable downside on one of three bugs** in this suite.

Because the unassisted baseline was already 100%, this pilot has **no headroom to detect positive lift**; it can only measure whether a lesson *harms* tasks the model already solves. Whether in-context injection provides positive lift on genuinely un-solved gotchas (private, post-cutoff, or non-memorized) is **untested here** and remains the central open question — the very question our pre-registered protocol names as the real test of Lore's value.

---

## 1. Introduction & Pre-Registered Hypotheses

AI coding agents repeatedly hit recurring gotchas: subtle framework behaviors, version-specific API shifts, and resource-leak traps. Lore's founding premise is that a global, executable, container-verified registry of procedural knowledge (each lesson carrying its own eval) would let agents retrieve verified lessons at inference time and avoid known failure modes. This pilot is the first empirical test of whether such injection helps a real model.

Our predictions were locked in `PROTOCOL.md` §3 at commit `403e5d3` **before any trial ran**:

- **Primary metric:** turns-to-correct-fix (capped at 6), graded by a mechanical containerized judge.
- **H1 (Treatment lift):** with the lesson, the agent solves in fewer turns and/or at a higher rate than control.
- **H0 (Null):** lesson injection produces no observable difference in solve rate or turns.
- **Pre-committed redundancy criterion:** if control solves a bug in $\le 2$ turns unaided, the model already holds the needed capability and in-context injection is *redundant* for that bug. This is a real — if disappointing — finding, and a signal that Lore's value must be sought on bugs the model cannot already solve.

We emphasize that the redundancy criterion was **pre-registered, not chosen after seeing the data**. The outcome below matched it, which is why we report the null/negative result with confidence rather than reframing it post hoc.

---

## 2. Methodology

### 2.1 Decoupled Dual-Verification Harness
To remove evaluation bias, grading is fully mechanical and decoupled from what the agent sees:

1. **Agent view (`bug_XXXX_buggy.py`):** the model receives the raw symptom and realistic code with giveaway comments and explicit test assertions stripped.
2. **Behavioral probe (`bug_XXXX_probe.py`):** an unseen harness imports the candidate module and measures runtime *behavior* (e.g. settled-transaction state, ping latency under load) — never anything the candidate prints.
3. **Dual-check judge (`bug_XXXX_judge.py`):** a candidate passes only if (A) it satisfies the positive behavioral assertion **and** (B) the untouched original buggy file still fails the same probe — proving the bug was real and the probe discriminates, guarding against false positives from environment variance or a neutered test.

A broken candidate (syntax/import/runtime error) is recorded as a clean, path-free candidate failure, distinct from any harness malfunction.

### 2.2 Temperature & Model Locking
All trials ran at `temperature=0.0` on `gemini-3.1-flash-lite`, isolating lesson presence as the single independent variable. Every bug's buggy file, probe, judge, and raw JSON transcripts are committed (see Appendix B).

---

## 3. Results

Three pre-registered bugs, 18 trials total.

| Bug ID | Domain / Gotcha | Control Solved | Treatment Solved | Result |
| :--- | :--- | :---: | :---: | :--- |
| `0002` | `asyncio.gather` detached-sibling side effects | **3 / 3** (turn 1) | **0 / 3** (turn 6) | **Negative lift (harm)** |
| `0005` | Async-generator `aclose()` cleanup deferral | **3 / 3** (turn 1) | **3 / 3** (turn 1) | **Null (redundant)** |
| `0006` | Default `run_in_executor` pool starvation | **3 / 3** (turn 1) | **3 / 3** (turn 1) | **Null (redundant)** |

**Summary:** Control solved **9/9 (100%)** at **1.00** mean turns; treatment solved **6/9 (66.7%)** at **2.67** mean turns. With a 100% control baseline, there was **zero headroom for positive lift** in this suite; the only outcomes available to the lesson were "neutral" or "worse."

---

## 4. Findings & Discussion

### 4.1 High unassisted baseline on the tested bugs
On all three `asyncio` gotchas, `gemini-3.1-flash-lite` produced a correct fix on turn 1 in every control trial (9/9), whether via memorized training data or general reasoning — a distinction this study does not attempt to separate. For these specific bugs, the model already possessed the capability, making in-context injection redundant. We make **no claim beyond these three bugs**; a 100% rate on a hand-picked trio is a statement about the trio, not about the model or the method in general.

### 4.2 A prescriptive lesson caused negative lift on `0002`
In control, the model solved `0002` in one turn by keeping `asyncio.gather` and adding `return_exceptions=True`, which lets all tasks complete so the non-failing accounts (1 and 3) appear in the final reconciliation. In treatment, a lesson that prescriptively promoted `asyncio.TaskGroup` as the modern "best practice" steered the model to replace `gather` with `TaskGroup`. Because `TaskGroup` **cancels sibling tasks on the first failure**, accounts 1 and 3 were cancelled and lost, failing the business requirement in **100% of treatment trials**. In later turns the model compounded the error into invalid syntax (mixing `except*` with a bare `except` on one `try`), never recovering within the turn cap.

> **Takeaway:** procedural knowledge that advocates a "best practice" without explicit, symptom-conditional boundaries carries active downside risk — it can override a correct, context-sensitive default. Lessons should be framed conditionally ("use X when Y holds; avoid X when Z"), never as unconditional replacements.

---

## 5. Scope, Limitations & Recommendations

### 5.1 Limitations
1. **Baseline ceiling (the dominant limitation).** Control solved 100% unaided, so this suite *cannot* measure positive lift. It measures only whether a lesson harms tasks the model already solves. Lore's actual value proposition — helping an agent on a bug it fails without help — is **not tested here**, because the sample contains no such bug.
2. **Single model.** Results are bounded to `gemini-3.1-flash-lite` at `temperature=0.0`; other architectures may have different baseline knowledge and different susceptibility to prescriptive framing.
3. **Small N.** Three trials per condition per bug isolates temperature-0 behavior but does not support statistical generalization.
4. **Non-differentiated baseline.** We measure unassisted solve rate but do not separate memorization from reasoning.

### 5.2 Recommendations for the next round
1. **Test the regime that matters: seed bugs where control *fails* (0/3 or 1/3).** Only against a non-zero failure floor can positive lift be observed. This is the experiment that would actually validate — or refute — Lore's premise.
2. **Scope lessons toward un-memorizable boundaries:** private/enterprise patterns, fast-moving post-cutoff API shifts, and non-deterministic environment gotchas — where a model is more likely to lack the answer parametrically.
3. **Enforce symptom-conditional phrasing** in the lesson schema, motivated directly by the `0002` failure, so a lesson cannot read as an unconditional "use X instead of Y."

---

## Appendix A: Candidate scenarios for a future round (NOT part of this study)

During development we informally spot-checked several additional gotchas — `asyncio.subprocess` pipe-buffer deadlock, Pydantic v2 `field_validator` on default values, Python 3.13 `asyncio.Queue.shutdown`, Pydantic `ConfigDict(defer_build=True)`, and FastMCP `Context` injection. **These were not run through the dual-verification harness, have no committed transcripts, and no solve-rate or lift is claimed from them.** They are listed only as candidates to be built out as proper, harnessed bugs in a future round — ideally chosen to include cases the model does *not* solve cold (per §5.2).

## Appendix B: Reproducibility

Buggy files, behavioral probes, dual-verification judges, the pre-registered protocol, and raw JSON trial transcripts for bugs `0002`, `0005`, and `0006` are archived in `experiments/proof-of-use/` in the `Soulfullmens/lore` repository. The runner (`run_pou.py`) sanitizes machine-specific paths from all logged results.

## Acknowledgements & Tooling

This work was carried out by the Lore project author. Development was assisted by AI coding tools (the Antigravity IDE and an LLM pair-programming assistant); all experimental design, pre-registration, and analysis decisions are the author's.
