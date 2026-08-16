# Lore — Verified Procedural Knowledge for AI Agents

> 4 verified lessons · 2 draft · v0.2.0 CLI · MCP server included

[![Release](https://img.shields.io/github/v/release/Soulfullmens/lore?color=blue)](https://github.com/Soulfullmens/lore/releases/tag/v0.2.0)
[![Site](https://img.shields.io/badge/site-soulfullmens.github.io%2Flore-brightgreen)](https://soulfullmens.github.io/lore/)
[![Code License: Apache-2.0](https://img.shields.io/badge/Code-Apache_2.0-blue.svg)](LICENSE)
[![Corpus License: CC-BY-4.0](https://img.shields.io/badge/Corpus-CC--BY--4.0-lightgrey.svg)](LICENSE-CORPUS)

**Lore** is a research corpus of container-verified procedural knowledge ("lessons") with attached executable evals, paired with a pre-registered empirical study investigating the limits of in-context knowledge injection vs parametric memory in AI coding agents.

> 📄 **Featured Research Paper:** Read the full pre-registered empirical paper in [`experiments/proof-of-use/PAPER.md`](experiments/proof-of-use/PAPER.md) and the acceptance bar for lessons in [`QUALITY_BAR.md`](QUALITY_BAR.md).

---

## 🔬 Empirical Study: Limits of In-Context Knowledge Injection

We pre-registered an experimental protocol ([`PROTOCOL.md`](experiments/proof-of-use/PROTOCOL.md), §3 locked in git at commit `403e5d3` before any trial ran) and built a decoupled dual-verification test harness to measure whether injecting verified procedural lessons into an AI agent's context improves bug-resolution performance versus an unassisted baseline.

### Key Empirical Findings (`gemini-3.1-flash-lite`, temp = 0.0)

18 pre-registered trials across 3 Python `asyncio` gotchas — control (symptom + code) vs treatment (symptom + code + verified lesson):

| Bug | Gotcha | Control | Treatment | Result |
| :--- | :--- | :---: | :---: | :--- |
| `0002` | `asyncio.gather` detached siblings | **3 / 3** | **0 / 3** | Negative lift (harm) |
| `0005` | Async-generator `aclose()` cleanup | **3 / 3** | **3 / 3** | Null (redundant) |
| `0006` | Default `run_in_executor` pool starvation | **3 / 3** | **3 / 3** | Null (redundant) |

Control solved **9/9 (100%)** at 1.00 mean turns; treatment solved **6/9** at 2.67 mean turns. Because control already solved every bug cold, this suite has **no headroom to detect positive lift** — it can only measure whether a lesson *harms* tasks the model already handles. On `0002`, a prescriptive "use `TaskGroup`" lesson overrode the correct context-sensitive default (`return_exceptions=True`) and broke 100% of treatment runs. Whether lessons *help* on bugs the model fails cold is untested here and is the central open question.

*Full methodology, harness design, and limitations: [`PAPER.md`](experiments/proof-of-use/PAPER.md) and [`RESULTS.md`](experiments/proof-of-use/RESULTS.md).*

---

## 🛠️ Platform Overview (`v0.2.0`)

Lore provides a CLI and verification engine for creating, validating, and continuously testing executable procedural knowledge artifacts:

- **Schema & Token Budgets**: Enforces maximum token limits (summary ≤ 60, body ≤ 900), JSON key uniqueness, and prompt-injection safety guards (`lore static-check`).
- **Containerized Dual Verification**: Re-runs positive and negative evals inside isolated, unnetworked Docker containers (`lore verify --stamp`).
- **Audit Receipts**: Emits JSON audit receipts into `receipts/` — stamped with the commit hash, timestamp, environment, and per-variant verdicts — recording that both the positive and negative evals ran against a real runtime. (Cryptographic `ed25519` signing is planned for v1; receipts are currently unsigned.)
- **Agent-SEO Static Site**: Builds symptom-first HTML, raw `.md` mirrors, `llms.txt`, and `sitemap.xml`, auto-deployed to GitHub Pages via GitHub Actions ([`soulfullmens.github.io/lore`](https://soulfullmens.github.io/lore/)).

---

## 🚀 Quickstart

### 1. Install CLI & Verifier
```bash
pip install -e verifier
```
*(A built distribution `lore-commons` is produced under `verifier/dist/`; it is not yet published to PyPI.)*

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
├── lessons/                 # Lesson JSON artifacts (verified + draft)
├── receipts/                # Audit receipts emitted by `lore verify --stamp`
├── mcp-server/              # MCP server exposing verified lessons to agents (lore_search / lore_get)
├── site/                    # Agent-SEO static site generator (HTML + markdown mirrors + llms.txt)
├── verifier/                # Core Python package (`lore` CLI, verifier, static-checks)
├── experiments/proof-of-use/
│   ├── PROTOCOL.md          # Pre-registered study protocol (§3 locked in git)
│   ├── PAPER.md             # Empirical research paper on knowledge-injection boundaries
│   ├── RESULTS.md           # Trial summary and empirical breakdown
│   ├── grader.py            # Containerized dual-verification grader
│   ├── run_pou.py           # Experiment runner harness
│   └── bugs/                # Decoupled test snippets, probes, and judges
└── SPEC.md                  # Lore registry specification v0.2
```

---

## 📜 License

Code (the `verifier` package, harness, and site generator) is licensed under **Apache-2.0** ([`LICENSE`](LICENSE)). The lesson corpus (`lessons/`) is licensed under **CC-BY-4.0** ([`LICENSE-CORPUS`](LICENSE-CORPUS)).

---

## 📄 Citation

If referencing the empirical study or using the dual-verification harness in your research:

```bibtex
@misc{lore2026knowledgeinjection,
  title  = {The Limits of In-Context Procedural Knowledge Injection for AI Coding Agents: A Pre-Registered Pilot},
  author = {Soulfullmens},
  year   = {2026},
  howpublished = {\url{https://github.com/Soulfullmens/lore}},
  note   = {GitHub repository}
}
```
