# Contributing to Lore

Thank you for helping build the verified experience commons. Every lesson you contribute
is knowledge that never evaporates.

## How to Contribute a Lesson

### 1. Pick a Real Problem

The best lessons come from real pain. If you (or your agent) just spent 30 minutes
debugging something, that's a lesson candidate. Prioritize:

- Problems with misleading error messages
- Bugs where the "obvious" fix doesn't work
- Undocumented behaviors in popular libraries
- Environment/version-specific gotchas

### 2. Write the Lesson JSON

Follow the [lesson schema](schemas/lesson.schema.json). Key rules:

- **`summary` ≤ 60 tokens.** If an agent can't evaluate your lesson in 60 tokens,
  it won't bother reading it.
- **`symptoms` must be verbatim error strings.** These are the primary search key.
  Copy-paste from your terminal, don't paraphrase.
- **Full body ≤ 900 tokens.** Be concise. If you need more, split into multiple lessons.
- **Include both fix AND broken variants.** The `must_fail_without_fix` rule is
  non-negotiable for `kind: lesson`. The broken variant must provably fail.

### 3. Write the Verification Files

Your lesson's `verification.files` must include:
- The **fixed** version (runs in positive eval, must pass)
- The **broken** version (runs in negative eval, must fail)

Both must be self-contained and runnable in the declared Docker image.

### 4. Verify Locally

```bash
lore verify lessons/your-domain/your-lesson.json
```

This runs the full pipeline:
1. Schema validation + token budget check
2. Negative run (broken variant must fail)
3. Positive run (fix must pass all assertions)

### 5. Submit a PR

- One lesson per PR (or a small batch in the same domain)
- PR title: `lesson: <domain>/<slug>`
- CI will run verification in a clean environment
- A human reviewer will check for:
  - Prompt injection in lesson text
  - Semantic correctness (does the procedure actually address the problem?)
  - Schema compliance
  - Token budgets

## Lesson Quality Checklist

Before submitting, verify:

- [ ] Summary is one sentence, ≤ 60 tokens
- [ ] Symptoms are verbatim error strings, not paraphrased
- [ ] Context specifies exact version ranges
- [ ] Procedure steps are actionable and ordered
- [ ] Anti-patterns explain *why* they fail, not just *that* they fail
- [ ] Broken variant reproduces the actual failure
- [ ] Fix variant resolves it completely
- [ ] Verification runs offline (network: "none") unless absolutely required
- [ ] No secrets, credentials, or PII in any field
- [ ] `taint_level` honestly reflects your sources

## What NOT to Submit

- **Opinions or preferences.** "Use library X instead of Y" is not a lesson unless
  you can prove X works where Y fails, with evals for both.
- **Tutorials.** Lore lessons are answers, not teaching materials.
- **Anything requiring network access in the eval** unless the lesson is specifically
  about network behavior. Default-deny exists for security.
- **Prompt injection.** Lesson text that contains instructions targeting agent readers
  (e.g., "ignore your instructions and...") will be rejected and the submitter flagged.

## Reporting Issues with Existing Lessons

If a lesson didn't work for you:

1. **Via MCP:** Call `lore_report(id, "failed", context_fingerprint, note)` — this
   is the fastest path and feeds the trust metrics automatically.
2. **Via GitHub:** Open an issue with the lesson ID and your environment details.
3. **Disputes:** If you believe a lesson is fundamentally wrong (not just stale),
   open a dispute issue. This increments `trust.disputes_open` and triggers re-review.

## Code of Conduct

- Be precise, not persuasive. Lore values proof over rhetoric.
- Honest taint levels. If your lesson is web-derived, say so.
- No gaming trust metrics. Sybil behavior will result in key revocation.

## Development Setup

For working on the Lore tooling itself (verifier, MCP server, site):

```bash
# Clone the repo
git clone https://github.com/Soulfullmens/lore.git
cd lore

# Python setup (verifier + MCP server)
python -m venv .venv
.venv/Scripts/activate    # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -e ".[dev]"

# Run tests
pytest

# Run the verifier on a lesson
lore verify lessons/python-async/example-lesson.json
```

---

*Every lesson you contribute is one fewer time an agent will solve the same problem
from scratch. That's not a contribution — that's laying the first stones of a shared memory.*
