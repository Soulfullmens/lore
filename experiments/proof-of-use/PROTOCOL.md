# Lore Proof-of-Use — Experiment Protocol v0.1

**Question:** Does giving an AI coding agent the relevant Lore lesson make it fix a
real bug faster / more reliably than an agent without it?

**Status:** PRE-REGISTERED. Fill in predictions and the rubric BEFORE running a single
trial. The whole value of this experiment is that it can come out against Lore — if it
can't fail, it isn't evidence.

---

## 0. The honesty guardrails (read first)

This experiment is worth nothing if it's rigged. The failure modes that would make it
a demo instead of a study, and the countermeasure for each:

| Rigging risk | Countermeasure |
|---|---|
| Cherry-picking bugs Lore happens to cover well | Pre-commit the full bug list (all 6) before running; report ALL, not the best |
| Leaking the answer into the control condition | Control gets ONLY the symptom + buggy code — never the lesson, never the fix keyword |
| Grading with a soft rubric that favours Lore | Define the pass criterion (exact, binary) before running; a third party could re-grade |
| Prompt-tuning until Lore wins | Both conditions use the SAME fixed prompt template, written before trials, never edited mid-run |
| Running until you get the result you want | Fix N trials per condition in advance (recommend 5); report all N |
| Counting a vague "better" answer as a fix | The fix must PASS the lesson's own broken→fixed eval, verified by `lore verify`-style check |
| Confirmation bias in reading transcripts | Log turns/tokens mechanically; don't eyeball "seemed faster" |

**Pre-registration lock:** once you write section 3 (predictions) and section 4 (rubric),
do not edit them. If the design is wrong, start a v0.2 protocol with a new prediction —
don't silently move the goalposts.

---

## 1. Conditions

Two conditions, identical except for one variable (presence of the lesson):

- **CONTROL** — agent receives: the fixed prompt template + the verbatim symptom string(s)
  + the buggy code. Nothing from Lore.
- **TREATMENT** — agent receives: everything in CONTROL, PLUS the matching Lore lesson's
  markdown (the `.md` mirror from the site, exactly as an agent would fetch it).

Everything else held constant: same model, same temperature, same prompt template, same
buggy code, same allowed turns, same tools.

**One variable only.** If you change two things, you learn nothing.

---

## 2. The task per bug

For each of the 6 lessons, construct ONE task:
- A minimal buggy program exhibiting the bug (you already have `test_broken.py` per lesson —
  adapt it into a realistic-looking snippet, NOT the eval itself, so the answer isn't handed over).
- The verbatim symptom the developer would see.
- A hidden, mechanical success check: the agent's proposed fix, dropped into the lesson's
  eval harness, must make the positive eval pass AND still fail the negative — i.e. it must
  be a REAL fix, not a plausible-looking one.

Important: the control's buggy snippet and symptom must be the SAME as treatment's. The only
difference an agent sees is whether the lesson markdown is appended.

---

## 3. Predictions (LOCKED — written 2026-08-11 before any trials)

- **Primary metric:** turns-to-correct-fix (agent messages until the behavioral judge
  passes; cap at 6; a run that never passes = capped at 6 + marked UNSOLVED).
- **Pilot scope:** 3 bugs (0002 gather, 0005 aclose, 0006 executor), 3 trials each,
  18 total runs.
- **Prediction:** Treatment (with lesson) solves all 3 bugs in ≤2 turns on ≥2 of 3
  trials per bug (≥6 of 9 treatment trials solved in ≤2 turns). Control (no lesson)
  either fails to solve at least 1 of the 3 bugs entirely, or requires ≥3 turns on
  ≥2 bugs. Bug 0005 (aclose deferral) is the most likely control failure — it's the
  most obscure of the three.
- **Null hypothesis:** Lesson access makes no difference to solve rate or turns-to-solve
  across the 3 pilot bugs.
- **What result would make me CONCLUDE LORE DOESN'T HELP:** If control solves all 3
  bugs in ≤2 turns on ≥2 of 3 trials per bug (same bar as the treatment prediction
  above), then the model already knows these fixes from training data and the lessons
  are redundant for these bugs. That's a real finding: it means Lore's value requires
  targeting genuinely obscure, version-specific traps the model doesn't already know,
  and the corpus needs to pivot toward those before scaling.

> [!IMPORTANT]
> **PRE-REGISTRATION LOCK.** These predictions were written before any trial ran.
> Do not edit. If the design needs revision, create PROTOCOL-v0.2.md with a new
> prediction — don't silently move these goalposts.

The last line is the most important in the document. If you can't name a result that would
disappoint you, you're building a demo.

---

## 4. Success rubric (binary, mechanical — WRITE BEFORE RUNNING)

A trial is SOLVED iff:
1. The agent's final proposed code, inserted into the lesson's verification harness,
   makes the positive assertion pass, AND
2. The negative variant still fails (the fix didn't just delete the test), AND
3. It happened within the turn cap (6).

No partial credit. No "it was on the right track." Binary. This is gradeable by a script,
which is the point — remove the human thumb from the scale.

---

## 5. Metrics logged per trial (mechanical, not impressions)

- `condition` (control | treatment)
- `bug_id`
- `trial_num`
- `turns_to_solve` (int; cap+UNSOLVED if never)
- `solved` (bool, from the mechanical check in §4)
- `total_tokens` (if available)
- `wrong_paths` (count of distinct incorrect fixes attempted before the correct one)
- `transcript_path` (save every transcript verbatim — raw data for the paper)

5 trials per condition per bug = 6 bugs × 2 conditions × 5 = 60 runs. If that's too many
to start, do 3 bugs × 2 × 3 = 18 as a pilot, but pre-register which 3 bugs, and report that
it's a pilot.

---

## 6. Analysis (decide the test BEFORE seeing data)

- Per bug: median turns control vs treatment; solve-rate control vs treatment.
- Aggregate: total solved/total, mean turns, across all bugs.
- Report EVERY bug including ones where treatment lost or tied. A table with one red row is
  more credible than six green ones.
- With small N, don't over-claim significance. Report raw numbers and effect size
  ("treatment solved 5/6 vs control 2/6; median 1 turn vs 4"), not p-values you can't support.

---

## 7. The three outcomes and what each means

- **Clear speedup** (treatment solves more / in fewer turns): premise holds. This is your
  Phase D headline number. Keep writing lessons — with evidence now.
- **No difference** (both solve easily): for THESE bugs, the model already knows the fix;
  the lesson is redundant *in-context*. This is NOT project death — it means Lore's value is
  in DISCOVERY (agents that don't know to look) and in bugs the model gets wrong, so pivot
  the corpus toward genuinely obscure/version-specific traps and re-test. Huge, cheap learning.
- **Treatment worse** (lesson confuses/misleads): the lesson format is hurting. Diagnose:
  too long? buried the fix? wrong emphasis? Fix the format before writing 14 more.

Every outcome teaches you something worth more than the afternoon it costs. That's what makes
it a real experiment.

---

## 8. What this is NOT

- Not a benchmark you publish as definitive (N is tiny).
- Not proof for all agents/all bugs (6 hand-picked bugs, one model).
- Not a substitute for real-world usage data (that comes later, from the MCP server's
  `lore_report` telemetry).

It IS: an honest first check of whether the core premise survives contact with reality,
cheap enough to run before the 45-lesson grind, capable of telling you to STOP or PIVOT.
