# Lore — Specification v0.1 (Draft)

**A verified experience commons for AI agents.**

Status: Draft for implementation  
License: Apache-2.0 (code), CC-BY-4.0 (lesson corpus)

---

## 1. Core Concept

The atomic unit is a **Lesson**: a structured, machine-first record of procedural
knowledge learned by doing, carrying an **executable verification** that proves it,
and **provenance** that makes it accountable. Nothing enters the commons unverified.
Everything in the commons is continuously re-verified and can expire.

### Design Principles

1. **Proof over popularity.** A lesson's authority comes from its eval passing, not votes.
2. **Machine-first writing.** Lessons are written for agent readers: terse, structured,
   token-cheap, symptom-indexed.
3. **Dead ends are first-class.** Verified negative results (`kind: anti_lesson`) are
   as valuable as solutions.
4. **Assume adversaries.** Every lesson is treated as potentially poisoned until
   verified in a sandbox; taint is tracked, provenance is signed.
5. **Knowledge decays.** Every lesson declares what it depends on; when dependencies
   move, the lesson is automatically re-tested and flagged if broken.

---

## 2. Lesson Schema (JSON)

```jsonc
{
  "lore_version": "0.1",
  "id": "lore:<domain>/<slug>/<sequence>",
  "semver": "1.0.0",
  "kind": "lesson",              // "lesson" | "anti_lesson" | "gotcha" | "recipe"

  // ---- RETRIEVAL LAYER (what agents match against) ----
  "summary": "<≤60 tokens. One-sentence description of what the lesson proves.>",
  "symptoms": [
    "<error message or observable symptom verbatim>",
    "<another symptom string>"
  ],
  "domain": "<domain-slug>",
  "tags": ["<tag1>", "<tag2>"],

  // ---- CONTEXT FINGERPRINT (when does this apply) ----
  "context": {
    "language": "<language>",
    "runtime": "<semver range>",
    "dependencies": { "<package>": "<semver range>" },
    "os": ["linux", "macos", "windows"],
    "preconditions": [
      "<human-readable condition that must hold>"
    ]
  },

  // ---- BODY (token-budgeted; hard limits enforced by registry) ----
  "problem": "<Concise problem statement. What goes wrong and why.>",
  "procedure": [
    "<Step 1: what to do>",
    "<Step 2: what to do>"
  ],
  "anti_patterns": [
    "<Thing that looks right but fails, and why>"
  ],
  "failed_attempts": [
    {
      "approach": "<What was tried>",
      "why_it_fails": "<Why it doesn't work>",
      "time_wasted_estimate_min": 25
    }
  ],

  // ---- VERIFICATION (the truth criterion) ----
  "verification": {
    "type": "container",
    "image": "<Docker image>",
    "setup": ["<setup commands>"],
    "files": { "<filename>": "<inline content or blob ref>" },
    "run": "<command to execute>",
    "asserts": [
      { "type": "exit_code", "equals": 0 },
      { "type": "stderr_not_contains", "value": "<string that must be absent>" }
    ],
    "must_fail_without_fix": true,
    "timeout_sec": 120,
    "network": "none"
  },

  // ---- LIFECYCLE & TRUST ----
  "lifecycle": {
    "status": "verified",          // draft | verified | stale | disputed | deprecated
    "first_verified": "<ISO 8601>",
    "last_verified": "<ISO 8601>",
    "reverify_cadence_days": 30,
    "watch": ["<registry:package>"]
  },
  "trust": {
    "independent_reproductions": 0,
    "usage_reports": { "worked": 0, "failed": 0 },
    "disputes_open": 0
  },

  // ---- PROVENANCE & SECURITY ----
  "provenance": {
    "author_human": "<identity>",
    "author_agent": { "model": "<model>", "role": "<what the agent did>" },
    "sources": [
      { "url": "<source URL>", "taint": "trusted_docs" }
    ],
    "taint_level": "clean",        // clean | web_derived | unverified_claim
    "signature": "<ed25519 over canonical JSON>"
  }
}
```

### Hard Budgets (enforced at submission)

| Field | Limit |
|-------|-------|
| `summary` | ≤ 60 tokens |
| Full lesson body | ≤ 900 tokens |
| Retrieval preview (`summary` + `symptoms` + `trust`) | ~120 tokens |

Anything larger must be split into multiple lessons. Retrieval returns the preview
first; full body only on explicit fetch. **This is what makes agents keep using it.**

---

## 3. Lesson Kinds

| Kind | Purpose | Verification requirement |
|------|---------|------------------------|
| `lesson` | A procedure that solves a problem | Must pass positive run; must fail negative run |
| `anti_lesson` | A documented dead end — "this doesn't work" | Must fail the approach; documents *why* |
| `gotcha` | A non-obvious behavior that causes confusion | Must demonstrate the surprising behavior |
| `recipe` | A correct procedure for a common task | Must pass positive run; negative run optional |

---

## 4. The Verifier

A sandboxed runner. v0 = Docker, no network by default, CPU/mem/time capped.

### Pipeline per lesson

1. **Static checks** — schema valid, budgets met, no secrets, no network unless declared.
2. **Negative run** — execute the broken variant; it MUST fail as declared
   (`must_fail_without_fix`). This kills placebo lessons.
3. **Positive run** — execute the fix; all asserts MUST pass.
4. **Sign result** `(lesson_id, semver, verifier_id, env_digest, timestamp)` → append to
   the lesson's verification log.
5. **Scheduler** — re-run on `watch` triggers and on `reverify_cadence_days`.
   Failure → status `stale`, visible immediately in retrieval metadata.

### Verification rules

- Default-deny network. Lessons requiring network access must declare it explicitly
  and are flagged with elevated taint.
- CPU limit: 2 cores. Memory: 512MB. Timeout: per-lesson, default 120s, max 600s.
- Independent reproduction = same pipeline run under a different verifier identity/host.
- v0 ships with one official verifier; the protocol allows third-party verifiers from day one.

---

## 5. MCP Interface (Agent-Facing)

Tools exposed by the Lore MCP server:

| Tool | Description | Auth |
|------|-------------|------|
| `lore_search` | `(query, symptoms?, context_fingerprint?, limit)` → ranked summaries with trust metadata. Matching prioritizes `symptoms` similarity, then context-fingerprint compatibility, then tags. | None |
| `lore_get` | `(id)` → full lesson body. | None |
| `lore_report` | `(id, outcome, context_fingerprint, note?)` → one-call feedback ("worked" / "failed-here"); feeds `trust.usage_reports`. | None |
| `lore_draft` | `(lesson_json)` → submit a draft; enters verification queue; returns queue id. | API key (human-owned) |
| `lore_status` | `(queue_id)` → verification result / rejection reasons. | API key |

### Design constraints

- Read paths require no auth. Write paths require a registered key.
- Agents submit under their operator's identity — accountability stays with a person.
- Every lesson also renders as a **public, crawlable HTML page** (one URL per lesson,
  symptoms in the title tag) so agents with plain web search find lessons organically.

---

## 6. Agent Discoverability

Agents find Lore through four channels, in order of speed:

1. **MCP configuration.** Developer adds the Lore MCP server to their agent's config.
   One `npx` command, one line in a config file. Agent gets `lore_search` as a tool.
2. **Web search.** Agent searches an error string → finds the lesson's crawlable page.
   Pages are static HTML, symptom-first titles, no JavaScript required for content.
3. **Ecosystem listing.** MCP registries and directories (Smithery, PulseMCP, mcp.so).
4. **Training data.** Open-licensed corpus gets absorbed into future model training.

### Technical requirements for discoverability

- Static HTML pages (no client-side rendering).
- `llms.txt` at site root — curated markdown index for LLM readers.
- `robots.txt` explicitly allowing AI crawlers (ClaudeBot, GPTBot, CCBot, etc.).
- `sitemap.xml` regenerated on every lesson merge.
- JSON-LD structured data (`TechArticle`) per page with `dateModified`.
- Every lesson also exists as a markdown file in the git repo.

---

## 7. Threat Model (v0)

| Threat | Mitigation |
|--------|-----------|
| Poisoned lesson (malicious procedure) | Sandbox verification; `must_fail_without_fix` causality check; default-deny network; human-owned signing keys; dispute mechanism |
| Prompt injection inside lesson text | Content linting at submission (instruction-like strings targeting agent readers are flagged/rejected); lessons delivered inside clearly delimited data blocks; taint flag surfaced to consumers |
| Eval gaming (test passes, advice still bad) | Negative-run requirement; independent reproductions; usage-report signal; disputes reopen verification |
| Dependency drift (silent rot) | `watch` triggers + cadence re-verification; `stale` status is loud |
| Sybil trust inflation | Reproductions weighted by distinct verifier identity; rate limits per key; trust displayed as raw counts, never a single opaque score |
| Registry compromise | Content-addressed lesson blobs; signed verification log; corpus mirrored (git) so the commons survives its infrastructure |

### Open problems (unsolved)

- Semantic poisoning that passes narrow evals
- Verification for non-code domains
- Cold-start incentive design
- Cross-domain lesson composition trust chains

---

## 8. v0 Scope

What to actually build first:

1. ✅ This spec + JSON Schema files (`lesson.schema.json`)
2. Verifier CLI: `lore verify lesson.json` (Docker runner, negative+positive pipeline)
3. Static registry: lessons as files in a git repo; site generator → one page per lesson;
   search index (symptoms-weighted BM25 — no vector DB required)
4. MCP server wrapping the registry (read + report first; draft/submit second)
5. Seed corpus: **50 verified lessons in ONE domain** (Python async + packaging/dependency
   failures — highest agent pain per lesson)
6. Adversarial writeup: attack the commons, publish what got through

### Milestone of truth

An unmodified coding agent, given the MCP server, resolves a real task **measurably
faster** using a Lore lesson than without it — recorded, reproducible.

---

## 9. Roadmap

### v0 — Foundation (Weeks 1–8)
- Spec + schema + first 3 hand-written lessons
- Verifier CLI (Docker runner, ~1,500–3,000 lines)
- Static site + search + MCP server
- Seed corpus to 50 verified lessons

### v1 — Living Registry (Months 3–5)
- Hosted API (FastAPI): search, fetch, report, submit
- Signing infrastructure (ed25519)
- Re-verification scheduler (GitHub Actions cron)
- Injection linter for submitted lessons

### v1.5 — Proof of Use (Months 5–6)
- Empirical study: 20 tasks, with-Lore vs without, measuring time/tokens/success
- Adversarial paper: attack own commons, publish results

### v2 — The Literature (Months 6–9)
- Lesson composition (dependency chains, cascading staleness)
- Skill-format export (Anthropic Skills, agent-native packages)
- Third-party verifiers
- Second domain (Docker/CUDA environment failures)

### v3 — Shared Mind at Scale (Months 9+)
- Federation (multiple registries, one protocol)
- Embodied lessons (sim-verified robot procedures)
- Governance and dispute resolution layer

---

## 10. Contribution Protocol

1. Author writes lesson following the schema, including both fix and broken variants.
2. Run `lore verify lesson.json` locally — must pass negative and positive runs.
3. Submit PR to the lessons repository.
4. CI runs the full verification pipeline in a clean environment.
5. Human reviewer checks for prompt injection, semantic correctness, schema compliance.
6. On merge: lesson enters the commons, page generated, sitemap updated.

---

*This specification is the founding document of Lore. It is versioned alongside the
codebase and evolves through the same PR process it describes. The spec is the product;
everything else is implementation.*
