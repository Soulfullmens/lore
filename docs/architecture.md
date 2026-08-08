# Lore Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│                    AGENT INTERFACES                      │
│                                                          │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │MCP Server│  │ Static Site  │  │  GitHub Repo      │  │
│  │(tool API)│  │ (crawlable)  │  │  (raw lessons)    │  │
│  └────┬─────┘  └──────┬───────┘  └─────────┬─────────┘  │
│       │               │                     │            │
├───────┴───────────────┴─────────────────────┴────────────┤
│                    REGISTRY LAYER                         │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Search Index │  │ Trust Store  │  │ Report Store  │  │
│  │ (BM25/symp) │  │ (raw counts) │  │ (worked/fail) │  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘  │
│         │                 │                   │          │
├─────────┴─────────────────┴───────────────────┴──────────┤
│                   VERIFICATION LAYER                      │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Schema Check │  │ Negative Run │  │ Positive Run  │  │
│  │ + Budgets    │  │ (must fail)  │  │ (must pass)   │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐                      │
│  │  Scheduler   │  │  Injection   │                      │
│  │  (re-verify) │  │  Linter      │                      │
│  └──────────────┘  └──────────────┘                      │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                    SANDBOX (Docker)                       │
│                                                          │
│  CPU: 2 cores │ Mem: 512MB │ Net: none (default)        │
│  Timeout: 120s (max 600s) │ Signed results              │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## Data Flow

### Lesson Submission
```
Author writes lesson.json
    │
    ▼
lore verify (local) ──→ Schema check ──→ Negative run ──→ Positive run
    │                                                          │
    ▼                                                          ▼
Submit PR ──→ CI verification (clean env) ──→ Human review ──→ Merge
    │
    ▼
Lesson enters commons ──→ Page generated ──→ Sitemap updated
                      ──→ Search index updated
                      ──→ MCP server serves it
```

### Lesson Query (Agent)
```
Agent hits error
    │
    ▼
lore_search(symptoms=[...]) ──→ BM25 match on symptoms
    │                              │
    ▼                              ▼
Receives summaries (~120 tokens)  Ranked by symptom match +
    │                              context compatibility
    ▼
lore_get(id) ──→ Full lesson body (≤900 tokens)
    │
    ▼
Agent applies procedure
    │
    ▼
lore_report(id, "worked"|"failed") ──→ Trust metrics updated
```

### Re-verification
```
Scheduler (daily cron)
    │
    ├──→ Check watch triggers (new package releases)
    │        │
    │        ▼
    │    Re-run verification pipeline
    │        │
    │        ├──→ Pass: update last_verified timestamp
    │        └──→ Fail: status → "stale", visible immediately
    │
    └──→ Check reverify_cadence_days
             │
             ▼
         Re-run if overdue
```

## Directory Structure (Target)

```
lore/
├── SPEC.md                          # Founding specification
├── README.md                        # Project overview
├── CONTRIBUTING.md                  # How to contribute
├── LICENSE                          # Apache-2.0 (code)
├── LICENSE-CORPUS                   # CC-BY-4.0 (lessons)
├── llms.txt                         # LLM discoverability
│
├── schemas/
│   └── lesson.schema.json           # JSON Schema
│
├── lessons/                         # The commons
│   ├── python-async/                # Domain: Python async
│   │   ├── aiohttp-session-*.json
│   │   └── ...
│   └── <other-domains>/
│
├── verifier/                        # Verification CLI
│   ├── src/
│   │   ├── __init__.py
│   │   ├── cli.py                   # CLI entry point
│   │   ├── schema_validator.py      # JSON Schema checks
│   │   ├── budget_checker.py        # Token budget enforcement
│   │   ├── docker_runner.py         # Container lifecycle
│   │   ├── assertion_engine.py      # Assert evaluation
│   │   ├── injection_linter.py      # Prompt injection detection
│   │   └── signer.py               # Ed25519 signing
│   ├── tests/
│   └── pyproject.toml
│
├── mcp-server/                      # MCP server
│   ├── src/
│   │   ├── server.py               # MCP protocol handler
│   │   ├── search.py               # BM25 search engine
│   │   └── report.py               # Usage report handler
│   └── pyproject.toml
│
├── site/                            # Static site generator
│   ├── public/
│   │   ├── robots.txt
│   │   └── sitemap.xml
│   ├── templates/
│   │   └── lesson.html
│   └── generator.py
│
└── docs/
    ├── architecture.md              # This file
    ├── threat-model.md              # Detailed threat analysis
    └── roadmap.md                   # Detailed roadmap
```
