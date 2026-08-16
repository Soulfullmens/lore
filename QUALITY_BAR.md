# Lore Quality Bar & Verification Standards

Lore is a research corpus of container-verified procedural knowledge ("lessons") with attached executable evaluations for AI coding agents. 

Because inaccurate, overly prescriptive, or unverified lessons actively degrade AI model performance ([see empirical findings](experiments/proof-of-use/PAPER.md)), every lesson in Lore must satisfy strict quality, causality, and safety criteria before being accepted into the registry.

---

## 🛡️ Core Verification Rules

### 1. Provable Causality (`broken_asserts` + `must_fail_without_fix`)
- **No Placebo Errors:** The negative run MUST fail by exhibiting the exact DECLARED symptom (e.g., throwing a specific exception or failing an assertion), never a artificial `sys.exit(1)` or hardcoded fail flag.
- **Proven Causality:** The untouched broken variant (`broken_files`) MUST fail the negative evaluation, proving that the bug is real and reproducible on the target environment.

### 2. Isolated Container Execution
- **Isolated Runtimes:** All evaluations run inside unnetworked, clean-room Docker containers (`python:3.12-slim`, etc.).
- **Audit Receipts:** Successful container verifications emit a JSON audit receipt into `receipts/` stamped with the commit hash, timestamp, and runtime output logs (`lore verify --stamp`).

### 3. Strict Token Budget Limits
To prevent context-window bloat and prompt pollution for agent readers:
- **Summary:** $\le 60$ tokens (cl100k_base encoding).
- **Body:** $\le 900$ tokens total across problem, procedure, anti-patterns, and failed attempts.
- Checked mechanically via `lore static-check` and GitHub Actions CI.

### 4. Non-Prescriptive Scoping (Default-Preservation)
- **Context Sensitivity:** Lessons must be conditionally formatted ("Use X when Y; avoid X when Z").
- **Human Review:** Every lesson is reviewed to ensure it does not advocate a broad "best practice" that overrides correct, context-sensitive model defaults (as observed in our empirical study on `asyncio.gather` vs `TaskGroup`).

### 5. Safety & Prompt Injection Guardrails
- **Linting:** All lesson content is automatically scanned via static linter for prompt injection patterns (`ignore previous instructions`, system tag breakouts, hex/base64 obfuscation).

---

## 📊 Verification Workflow

```bash
# 1. Validate schema, token budgets, and injection lints
lore static-check lessons/python-async/asyncio-gather-detached-siblings-0002.json

# 2. Re-run container evals in Docker & stamp cryptographic audit receipt
lore verify lessons/python-async/asyncio-gather-detached-siblings-0002.json --stamp
```
