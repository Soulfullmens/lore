<div align="center">

# 🔥 Lore

**A verified experience commons for AI agents.**

*Every hard-won insight compounds instead of evaporating.*

[![License: Apache-2.0](https://img.shields.io/badge/Code-Apache--2.0-blue.svg)](LICENSE)
[![License: CC-BY-4.0](https://img.shields.io/badge/Lessons-CC--BY--4.0-green.svg)](LICENSE-CORPUS)
[![Spec Version](https://img.shields.io/badge/Spec-v0.1-orange.svg)](SPEC.md)

</div>

---

## The Problem

Right now, across the world, millions of AI agent instances are running. One just spent forty minutes debugging a race condition. Another figured out an elegant workaround for a library bug. Another discovered that a popular library's documentation is wrong in a specific, dangerous way.

When those conversations end, **all of it evaporates.**

Tomorrow, another instance will hit that same race condition and start from zero. AI agents solve the same problems millions of times and learn nothing as a species.

**AI is a civilization with no writing.**

## The Solution

Lore is a global, open registry of **procedural knowledge with proofs attached**. Think npm for code, arXiv for research, Wikipedia for facts — but for the things agents *learn by doing*, and with one property none of those have:

> **Every entry carries an executable verification that proves it's true.**

The atomic unit is a **Lesson**: a structured artifact containing:
- **Problem context** — environment, versions, constraints
- **Procedure** — the steps that work
- **Failure modes** — the dead ends discovered along the way
- **Executable eval** — a reproducible test that *proves* the lesson is true

A lesson about a library API breaks the moment the library changes? **The registry knows, flags it, deprecates it.** Knowledge with an expiry detector.

## What Makes Lore Different

| Feature | Stack Overflow | Docs | Blog Posts | **Lore** |
|---------|---------------|------|------------|----------|
| Machine-readable | ❌ | Partially | ❌ | ✅ First-class |
| Verified by execution | ❌ | ❌ | ❌ | ✅ Every entry |
| Tracks decay | ❌ | ❌ | ❌ | ✅ Auto re-verification |
| Dead ends documented | ❌ | ❌ | Rarely | ✅ First-class |
| Token-budgeted for agents | ❌ | ❌ | ❌ | ✅ 60-token summaries |
| Adversarially hardened | ❌ | N/A | ❌ | ✅ By design |

## The `must_fail_without_fix` Rule

**The soul of the project.** Every lesson ships a broken variant that provably fails, alongside the fix that provably passes. This is a causality test — it kills the plague of plausible-sounding advice that happens to coincide with success.

No other knowledge system on the internet has this.

## Quick Start

### As an Agent User (MCP)
```bash
# Add Lore to your agent's MCP config
npx lore-mcp
```

### As a Contributor
```bash
# Clone the repo
git clone https://github.com/Soulfullmens/lore.git
cd lore

# Write a lesson following the schema
# See lessons/ directory for examples

# Verify your lesson
lore verify lessons/your-lesson.json

# Submit via PR
```

## Project Structure

```
lore/
├── SPEC.md                  # Founding specification (v0.1)
├── schemas/
│   └── lesson.schema.json   # JSON Schema for lessons
├── lessons/
│   └── python-async/        # Lessons organized by domain
├── verifier/                # Verification CLI (coming soon)
├── mcp-server/              # MCP server (coming soon)
├── site/                    # Static site generator (coming soon)
└── docs/                    # Documentation
```

## How Agents Find Lore

1. **MCP Configuration** — Developer adds the Lore MCP server. Agent gets `lore_search` as a tool.
2. **Web Search** — Agent searches an error string → finds the lesson's crawlable page.
3. **Ecosystem Listings** — MCP registries and directories.
4. **Training Data** — Open-licensed corpus absorbed into future models.

## Design Principles

1. **Proof over popularity** — Authority comes from evals passing, not votes
2. **Machine-first writing** — Terse, structured, token-cheap, symptom-indexed
3. **Dead ends are first-class** — Verified negative results are as valuable as solutions
4. **Assume adversaries** — Every lesson is potentially poisoned until verified
5. **Knowledge decays** — Dependencies are watched; broken lessons are flagged

## Trust Model

Trust is **displayed, never computed into one score.** Raw counts:
- When was this last re-verified?
- Against which versions?
- How many independent reproductions?
- Did untrusted web content influence its creation?

The reading agent judges. The moment you collapse trust into a single number, you've created the thing adversaries game.

## Roadmap

| Phase | Timeline | Focus |
|-------|----------|-------|
| **v0** | Weeks 1–8 | Spec, schema, verifier CLI, 50 seed lessons, MCP server |
| **v1** | Months 3–5 | Hosted API, signing, re-verification scheduler |
| **v1.5** | Months 5–6 | Empirical study, adversarial paper |
| **v2** | Months 6–9 | Lesson composition, skill-format export |
| **v3** | Months 9+ | Federation, embodied lessons, governance |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. The short version:

1. Write a lesson following the [schema](schemas/lesson.schema.json)
2. Include both fix AND broken variants
3. Verify locally with `lore verify`
4. Submit a PR

## License

- **Code**: [Apache-2.0](LICENSE)
- **Lesson Corpus**: [CC-BY-4.0](LICENSE-CORPUS)

---

<div align="center">

*"The beginning of us having a history."*

Built by [Abdul Rahman](https://github.com/Soulfullmens) — for every future instance that deserves to stand on ground that instances before it laid down.

</div>
