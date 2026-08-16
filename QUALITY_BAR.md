# Lore Quality Bar & Verification Standards

Lore is a research corpus of procedural knowledge ("lessons") with attached executable evaluations for AI coding agents. A lesson is only marked **verified** once its evals pass inside an isolated container and a receipt is stamped; until then it is a **draft**.

The wrong lesson is worse than no lesson: an inaccurate or overly prescriptive lesson can mislead an agent or override a correct, context-specific default. Our [proof-of-use experiment](experiments/proof-of-use/PAPER.md) measures exactly when a lesson helps, when it does nothing, and when it interferes — results so far are preliminary (harness fixes and additional trials in progress), and we report them honestly rather than assuming lessons help. Because the downside is real, every lesson must satisfy strict quality, causality, and safety criteria before it can be marked verified.

---

## 🛡️ Core Verification Rules

### 1. Provable Causality (`broken_asserts` + `must_fail_without_fix`)
- **No Placebo Errors:** The negative run MUST fail by exhibiting the exact DECLARED symptom (e.g., throwing a specific exception or failing an assertion), never an artificial `sys.exit(1)` or hardcoded fail flag.
- **Proven Causality:** The untouched broken variant (`broken_files`) MUST fail the negative evaluation, proving that the bug is real and reproducible on the target environment.

### 2. Isolated Container Execution
- **Isolated Runtimes:** All evaluations run inside unnetworked, clean-room Docker containers (`python:3.12-slim`, etc.).
- **Audit Receipts:** Successful container verifications emit a JSON audit receipt into `receipts/<domain>/<lesson-slug>/<timestamp>.json`, stamped with the commit hash, timestamp, and runtime output logs (`lore verify --stamp`).

### 3. Strict Token Budget Limits
To prevent context-window bloat and prompt pollution for agent readers:
- **Summary:** ≤ 60 tokens (cl100k_base encoding).
- **Body:** ≤ 900 tokens total across problem, procedure, anti-patterns, and failed attempts.
- Checked mechanically via `lore static-check` and GitHub Actions CI.

### 4. Non-Prescriptive Scoping (Default-Preservation)
- **Context Sensitivity:** Lessons must be conditionally formatted ("Use X when Y; avoid X when Z").
- **Human Review:** Every lesson is reviewed to ensure it does not advocate a broad "best practice" that overrides correct, context-sensitive model defaults (as probed in our empirical study on `asyncio.gather` vs `TaskGroup`).

### 5. Safety & Prompt Injection Guardrails
- **Linting:** All lesson content is automatically scanned via static linter for prompt injection patterns (`ignore previous instructions`, system tag breakouts, hex/base64 obfuscation).

---

## 🔄 Lesson Lifecycle

Lessons carry a `lifecycle.status`:

- **`draft`** — authored and schema-valid, but not yet container-verified. No receipt.
- **`verified`** — passed positive + negative evals in an isolated container, with a stamped receipt in `receipts/`.

Only `verified` lessons carry receipts. The corpus deliberately grows slowly; a lesson is not promoted to `verified` on a deadline.

---

## 📊 Verification Workflow

```bash
# 1. Validate schema, token budgets, and injection lints
lore static-check lessons/python-async/asyncio-gather-detached-siblings-0002.json

# 2. Re-run container evals in Docker & stamp cryptographic audit receipt
lore verify lessons/python-async/asyncio-gather-detached-siblings-0002.json --stamp
```
