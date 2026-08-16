# Lore Proof-of-Use Pilot Study Results (v0.2 Updated)

**Date:** August 2026  
**Model:** `gemini-3.1-flash-lite` (temperature = 0.0)  
**Protocol:** Pre-registered in `PROTOCOL.md` (§3 locked prior to execution)

---

## 📊 Summary Table

| Condition | Solved / Total | Mean Turns to Solve |
| :--- | :---: | :---: |
| **Control** (No Lore Lesson) | **9 / 9 (100%)** | **1.00** |
| **Treatment** (With Lore Lesson) | **6 / 9 (66.7%)** | **2.67** |

---

## 🔍 Detailed Breakdown per Bug

| Bug ID | Gotcha / Topic | Control Solved | Treatment Solved | Outcome Type |
| :--- | :--- | :---: | :---: | :--- |
| `0002` | `asyncio.gather` detached siblings | **3 / 3** (turn 1) | **0 / 3** (turn 6) | **Negative Lift / Over-prescriptive Harm** |
| `0005` | Async generator `aclose` cleanup | **3 / 3** (turn 1) | **3 / 3** (turn 1) | **Null / Model Redundancy** |
| `0006` | Default `run_in_executor` thread pool starvation | **3 / 3** (turn 1) | **3 / 3** (turn 1) | **Null / Model Redundancy** |

---

## 💡 Key Empirical Insights

### 1. `0002` — Prescriptive Lessons Can Override Correct Model Defaults
- **Without the lesson (Control):** `gemini-3.1-flash-lite` solved the problem in 1 turn by retaining `asyncio.gather` with `return_exceptions=True`, allowing all accounts to be processed and inspected.
- **With the lesson (Treatment):** The lesson emphasized `asyncio.TaskGroup` as a modern best practice. The model followed the lesson prescriptively, using `TaskGroup` which automatically cancels remaining sibling tasks when account 2 fails. This caused accounts 1 and 3 to be cancelled and lost, failing the business requirement.
- **Takeaway:** Prescriptive lesson phrasing ("use X instead of Y") carries active downside risk by overriding valid, context-sensitive model defaults. Lessons must be strictly conditional ("use X when condition A; use Y when condition B").

### 2. Baseline Ceiling Effect (100% Control Solve)
- Control solved **9 out of 9 trials in 1.00 turn**.
- **Headroom Limit:** Because the baseline model solved all three gotchas cold without assistance, there was **zero headroom for positive performance lift** ($0 \rightarrow 1$) in this trial suite.
- **Scope of Result:** This trial demonstrates the *downside risk* of naive knowledge injection on known tasks. It does *not* measure Lore's performance on tasks where unassisted control fails (0/3).

---

## ⚠️ Threats to Validity

1. **Baseline Ceiling:** Because control solved 100% of bugs unaided, this trial suite cannot evaluate positive lift on un-memorized or post-cutoff gotchas.
2. **Sample Size ($N=3$):** 3 trials per condition per bug isolates temperature-0 behavior for `gemini-3.1-flash-lite` but does not generalize to all model architectures.
3. **Single Model Scope:** Results are bounded to `gemini-3.1-flash-lite` at `temperature=0.0`.
