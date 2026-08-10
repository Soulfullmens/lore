# Lore Proof-of-Use Pilot Study Results (v0.1)

**Date:** 2026-08-11  
**Model:** `gemini-3.1-flash-lite` (temperature = 0.0)  
**Protocol:** Pre-registered in `PROTOCOL.md` (§3 locked prior to execution)

---

## 📊 Summary Table

| Condition | Solved / Total | Mean Turns to Solve |
| :--- | :---: | :---: |
| **Control** (No Lore Lesson) | **6 / 9** | **2.67** |
| **Treatment** (With Lore Lesson) | **3 / 9** | **4.33** |

---

## 🔍 Detailed Breakdown per Bug

| Bug ID | Gotcha / Topic | Control Solved | Treatment Solved | Outcome Type |
| :--- | :--- | :---: | :---: | :--- |
| `0002` | `asyncio.gather` detached siblings | 3 / 3 | 0 / 3 | **Degradation / Over-prescriptive Harm** |
| `0005` | Async generator `aclose` cleanup | 3 / 3 | 3 / 3 | **Null / Model Redundancy** |
| `0006` | Default `run_in_executor` starvation | 0 / 3 | 0 / 3 | **Instrument Failure (Hardware concurrency capacity)** |
| `probe 1` | `asyncio.subprocess` pipe buffer deadlock | 1 / 1 (cold) | — | **Null / Model Redundancy** (Model supplied `communicate()` cold) |
| `probe 2` | Pydantic v2 `field_validator` on defaults | 1 / 1 (cold) | — | **Null / Model Redundancy** (Model supplied `model_validator` cold) |

---

## 💡 Key Empirical Insights

1. **`0002` — Prescriptive Lessons Can Override Correct Model Defaults**:
   - Without the lesson, `gemini-3.1-flash-lite` reached for `return_exceptions=True` (correct for "all results required").
   - With the lesson (which emphasized `TaskGroup` as a modern best practice), the model forced `TaskGroup`, which cancels siblings when one task fails. This caused sibling outcomes to be lost, failing the specific completion requirement.
   - **Takeaway:** Lessons MUST be strictly conditional ("use X ONLY when Y") rather than prescriptively recommending a "best practice" that overrides correct context-sensitive model defaults.

2. **Standard-Library & Major Framework Gotchas Are Memorized**:
   - `gemini-3.1-flash-lite` correctly diagnosed and fixed `aclose` generator cleanup, 1MB `asyncio.subprocess` pipe buffer deadlocks, AND Pydantic v2 default validation cold without assistance.
   - **Takeaway:** For standard library and major framework gotchas heavily present in training sets, in-context lesson injection provides zero marginal lift. Lore's true value proposition relies on obscure, rapidly evolving, or post-cutoff package gotchas.

3. **`0006` — Instrument Failure (Dual-Check Verification Worked)**:
   - On multi-core host hardware, the default thread pool size (`min(32, cpu_count+4)`) was large enough that 8 blocking calls did not starve the ping call (`probe invalid`).
   - **Takeaway:** The dual-check judge successfully detected that the bug was not manifesting on the runner machine and rejected all trials rather than recording false positives.

---

## 🎯 Next Actions

- Refine lesson schema/format to enforce explicit symptom-conditional scoping.
- Pivot corpus selection toward obscure / version-specific edge cases.
- Update bug `0006` snippet to dynamically scale worker pressure to CPU count.
