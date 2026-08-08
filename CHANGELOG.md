# Changelog

All notable changes to the Lore specification and corpus.

## [v0.2] — 2026-08-08

### The Origin Story

Within 48 hours of the founding commit, applying Lore's own standard ("run it
before you claim it") to the seed corpus falsified one lesson's core premise
(a widely believed asyncio myth), exposed that both negative-run designs were
placebo evidence, and surfaced a failure mode (exit-0 failure) that the v0.1
schema could not express. The spec absorbed all three as v0.2. This is the
project working exactly as designed — on itself, first.

### Added

- **`broken_asserts`** — required when `must_fail_without_fix` is true. The negative
  run must exhibit the *declared symptom*, not merely fail. A nonzero exit code alone
  proves nothing (a script can hardcode failure); some real failure modes exit 0
  (e.g., `Unclosed client session` warnings on stderr). Causality is established by
  symptom, not by exit status.
- **`setup_network`** — network access during setup phase only (`none | packages | full`,
  default `packages`). Split from `network` which now governs only the eval runs.
  "The eval runs offline" is a per-phase, provable claim.
- **Behavior-gated symptom output rule** — broken variants must gate symptom output on
  observed runtime behavior; unconditional prints are placebo evidence and rejected in review.
- **Verbatim symptoms rule** — symptoms must be captured from real runs, not from memory.
- **CI enforcement** — new `check-v02-rules` job validates `broken_asserts` presence and
  `lore_version` on every PR.

### Changed

- `network` field now only accepts `none | full` (removed `limited`).
- Eval gaming threat mitigation updated in threat model to include `broken_asserts`.
- CONTRIBUTING.md checklist expanded with v0.2 rules.

### Corpus Changes

| Lesson | Version | Change |
|---|---|---|
| aiohttp-session-close-0001 | 1.0.0 → **1.1.0** | Natural broken variant (no hardcoded exit); exit-0 failure mode with symptom on stderr; `broken_asserts` with `exit_code: 0` + `stderr_contains` |
| asyncio-gather-0002 | 1.0.0 → **2.0.0** | **Core claim falsified.** Renamed from `silent-exception` to `detached-siblings`. v1 said gather cancels siblings — it does not (per Python docs: "won't be cancelled and will continue to run"). Rewritten around the real behavior. Old file deleted. Falsification recorded in `failed_attempts`. |
| asyncio-run-nested-0003 | 1.0.0 → **1.1.0** | Natural broken variant; verbatim modern error string; removed misleading `run_coroutine_threadsafe` demo from fix eval |

### Removed

- `network: "limited"` — replaced by `setup_network` / `network` split.
- `asyncio-gather-silent-exception-0002.json` — deleted (myth-based lesson replaced by
  corrected `asyncio-gather-detached-siblings-0002.json`).

## [v0.1] — 2026-08-08

### Added

- Founding specification (SPEC.md)
- JSON Schema (`lesson.schema.json`)
- 3 seed lessons in `python-async` domain
- GitHub Actions CI (schema validation, token budgets, injection linting)
- Agent discoverability stack (`llms.txt`, `robots.txt`)
- Dual licensing: Apache-2.0 (code), CC-BY-4.0 (lessons)
- Architecture documentation
- Contributing guidelines
- GitHub issue templates (disputes, failure reports)
