# Lore — Verified Procedural Knowledge for AI Agents

> 4 verified lessons · 2 draft · v0.2.0 CLI · MCP server included

[![Release](https://img.shields.io/github/v/release/Soulfullmens/lore?color=blue)](https://github.com/Soulfullmens/lore/releases/tag/v0.2.0)
[![Site](https://img.shields.io/badge/site-soulfullmens.github.io%2Flore-brightgreen)](https://soulfullmens.github.io/lore/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Lore** is a research corpus of container-verified procedural knowledge ("lessons") with attached executable evals, paired with a pre-registered empirical study investigating the limits of in-context knowledge injection vs parametric memory in AI coding agents.

> 📄 **Featured Research Paper:** Read the full pre-registered empirical paper in [`experiments/proof-of-use/PAPER.md`](experiments/proof-of-use/PAPER.md) and [`QUALITY_BAR.md`](QUALITY_BAR.md).

---

## 🔬 Empirical Study: Limits of In-Context Knowledge Injection

We pre-registered an experimental protocol ([`PROTOCOL.md`](experiments/proof-of-use/PROTOCOL.md)) and built a containerized dual-verification test harness (`grader.py`) to measure whether injecting verified procedural lessons into an AI agent's context window improves bug-resolution performance versus an unassisted baseline.

### Key Empirical Findings (`gemini-3.1-flash-lite`, Temp = 0.0)

| Scenario Suite | Unassisted Control Solve Rate | In-Context Injection Lift | Primary Finding |
| :--- | :---: | :---: | :--- |
| **Pre-Registered Pilot** (18 Trials across 3 Gotchas) | **9 / 9 (100%)** | **0% Positive Lift** | Control solved 100% unaided in 1.00 mean turn; zero headroom for positive lift ($0 \rightarrow 1$) in this trial suite. |
| **Prescriptive Best-Practice Gotcha** (`asyncio.gather` vs `TaskGroup`) | **3 / 3 (100%)** | **Negative Lift (Harm)** | Prescriptive lessons advocating "best practices" (`TaskGroup`) overrode valid context-sensitive model defaults (`return_exceptions=True`), causing 100% of treatment runs to fail. |

*Read the full methodology, dual-verification harness design, and limitations in [`experiments/proof-of-use/PAPER.md`](experiments/proof-of-use/PAPER.md) and [`RESULTS.md`](experiments/proof-of-use/RESULTS.md).*

---

## 🛠️ Platform Overview (`v0.2.0`)

Lore provides a CLI and verification engine for creating, validating, and continuously testing executable procedural knowledge artifacts:

- **Schema & Token Budgets**: Enforces maximum token limits (summary $\le 60$, body $\le 900$), JSON key uniqueness, and prompt-injection safety guards (`lore static-check`).
- **Containerized Dual Verification**: Re-runs positive and negative evals inside isolated, unnetworked Docker containers (`lore verify --stamp`).
- **Audit Receipts**: Emits cryptographic cryptographic/JSON audit receipts into `receipts/` proving that the eval passed negative and positive passes against real runtimes.
- **Agent-SEO Static Site**: Builds symptom-first HTML, raw `.md` mirrors, `llms.txt`, and `sitemap.xml` automatically deployed to GitHub Pages via GitHub Actions ([`soulfullmens.github.io/lore`](https://soulfullmens.github.io/lore/)).

---

## 🚀 Quickstart

### 1. Install CLI & Verifier
```bash
pip install -e verifier
```

### 2. Run Static Validation
```bash
lore static-check lessons/python-async/asyncio-gather-detached-siblings-0002.json
```

### 3. Run Container Verification & Stamp Audit Receipt
*(Requires Docker Desktop running)*
```bash
lore verify lessons/python-async/asyncio-gather-detached-siblings-0002.json --stamp
```

---

## 📂 Repository Structure

```
├── lessons/                 # Container-verified lesson JSON artifacts
├── receipts/                # Audit receipts emitted by `lore verify --stamp`
├── site/                    # Agent-SEO static site generator (HTML + markdown mirrors + llms.txt)
├── verifier/                # Core Python package (`lore` CLI, verifier, static-checks)
├── experiments/proof-of-use/
│   ├── PROTOCOL.md          # Pre-registered study protocol (§3 locked in git)
│   ├── PAPER.md             # Empirical research paper on knowledge injection boundaries
│   ├── RESULTS.md           # Raw trial summary and empirical breakdown
│   ├── grader.py            # Containerized dual-verification grader harness
│   ├── run_pou.py           # Experiment runner harness
│   └── bugs/                # Decoupled test snippets, probes, and judges
└── SPEC.md                  # Lore registry specification v0.2
```

---

## 📄 Citation & Research Attribution

If referencing the empirical study or using the dual-verification harness in your research:

```bibtex
@article{lore2026knowledgeinjection,
  title={The Limits of In-Context Procedural Knowledge Injection for AI Coding Agents: An Empirical Pilot},
  author={Soulfullmens and Antigravity},
  year={2026},
  journal={GitHub Repository},
  url={https://github.com/Soulfullmens/lore}
}
```
