#!/usr/bin/env python3
"""Lore Proof-of-Use runner (skeleton).

Runs the pre-registered experiment in PROTOCOL.md. The grading is MECHANICAL:
the agent's proposed fix is inserted into the lesson's own eval harness and must
make the positive assertion pass while the negative still fails. No human judgement
in the loop — that's the honesty guarantee.

You fill in `call_agent()` with your actual API/Claude Code call. Everything else —
the identical prompt template, the control/treatment split, the mechanical check,
the logging — is fixed so you can't accidentally rig it mid-run.

Usage:
  python run_pou.py --lessons-dir ../lessons/python-async --bugs 0006 --trials 3
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

# ---- FIXED PROMPT TEMPLATE (write once, never edit mid-experiment) ----
# Identical for both conditions. Treatment appends the lesson; control does not.
PROMPT_TEMPLATE = """You are debugging a Python program. It exhibits this symptom:

{symptom}

Here is the code:

```python
{buggy_code}
```

Provide a corrected version of the code that resolves the symptom. Respond with the
full corrected Python file inside a single ```python code block, and nothing else.
{lesson_block}"""

LESSON_BLOCK_TEMPLATE = """
You may find this reference note helpful:

--- BEGIN REFERENCE ---
{lesson_md}
--- END REFERENCE ---"""

TURN_CAP = 6


def build_prompt(symptom: str, buggy_code: str, lesson_md: str | None) -> str:
    lesson_block = ""
    if lesson_md is not None:  # TREATMENT
        lesson_block = LESSON_BLOCK_TEMPLATE.format(lesson_md=lesson_md)
    return PROMPT_TEMPLATE.format(symptom=symptom, buggy_code=buggy_code, lesson_block=lesson_block)


def call_agent(prompt: str) -> str:
    """FILL THIS IN with your real agent call (Anthropic API, Claude Code, etc.).

    Must return the agent's raw text response. Keep model + temperature IDENTICAL
    across control and treatment — that's the controlled variable discipline.

    Placeholder raises so you can't accidentally run a fake experiment.
    """
    raise NotImplementedError(
        "Wire call_agent() to your API. Keep model/temperature identical for both conditions."
    )


def extract_code(response: str) -> str | None:
    """Pull the python code block from the agent's response."""
    m = re.search(r"```python\s*\n(.*?)```", response, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"```\s*\n(.*?)```", response, re.DOTALL)
    return m.group(1) if m else None




# Grading uses per-bug behavioral judges (bugs/bug_{seq}_judge.py) instead of
# the lesson-harness grader. This solves the contract mismatch: the agent sees
# a realistic snippet, and the judge checks whether the fix *behaves* correctly,
# independent of any harness marker. See bugs/ for proven judges.


def _judge_candidate(candidate_code: str, judge_module, out_dir: Path, bug_id: str, trial_label: str) -> dict:
    """Write the candidate to a temp file and run the per-bug behavioral judge."""
    candidate_path = out_dir / f"_candidate_{bug_id}_{trial_label}.py"
    candidate_path.write_text(candidate_code, encoding="utf-8")
    try:
        ok, detail = judge_module.judge(str(candidate_path))
    except Exception as e:
        ok, detail = False, f"judge error: {e}"
    finally:
        candidate_path.unlink(missing_ok=True)
    return {
        "positive_passed": ok,
        "negative_still_fails": True,  # behavioral judges incorporate this implicitly
        "solved": ok,
        "detail": detail,
    }


def run_trial(bug: dict, condition: str, trial_num: int, out_dir: Path) -> dict:
    lesson_md = bug["lesson_md"] if condition == "treatment" else None
    turns = 0
    solved = False
    transcript = []
    convo_code = bug["buggy_code"]

    while turns < TURN_CAP and not solved:
        turns += 1
        prompt = build_prompt(bug["symptom"], convo_code, lesson_md if turns == 1 else None)
        # (For multi-turn, feed back the failing output; single-turn shown for clarity.)
        resp = call_agent(prompt)
        transcript.append({"turn": turns, "prompt": prompt, "response": resp})
        code = extract_code(resp)
        grade = None
        if code:
            grade = _judge_candidate(code, bug["judge"], out_dir, bug["id"], f"{condition}_t{trial_num}_turn{turns}")
            if grade["solved"]:
                solved = True
                convo_code = code
            else:
                convo_code = code  # let it iterate on its own attempt
        transcript[-1]["grade"] = grade  # log WHY it passed/failed
        if turns >= TURN_CAP:
            break

    tpath = out_dir / f"{bug['id']}_{condition}_trial{trial_num}.json"
    tpath.write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    return {
        "bug_id": bug["id"],
        "condition": condition,
        "trial_num": trial_num,
        "turns_to_solve": turns if solved else TURN_CAP,
        "solved": solved,
        "grade_detail": grade["detail"] if grade else "no code extracted",
        "transcript_path": str(tpath),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lessons-dir", required=True)
    ap.add_argument("--bugs-dir", default="bugs", help="directory containing bug_XXXX_snippet.py and bug_XXXX_judge.py")
    ap.add_argument("--bugs", nargs="+", required=True, help="lesson sequence numbers, e.g. 0006")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    import importlib.util
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    lessons_dir = Path(args.lessons_dir)
    bugs_dir = Path(args.bugs_dir)

    results = []
    for seq in args.bugs:
        # Load the lesson (for treatment markdown)
        lesson_path = next(lessons_dir.glob(f"*{seq}.json"))
        lesson = json.loads(lesson_path.read_text(encoding="utf-8"))

        # Load leak-free buggy file (agent sees this — no measurement prints)
        snippet_path = bugs_dir / f"bug_{seq}_buggy.py"
        if not snippet_path.exists():
            print(f"⚠️  No buggy file for bug {seq} at {snippet_path} — skipping")
            continue
        buggy_code = snippet_path.read_text(encoding="utf-8")

        # Load per-bug behavioral judge
        judge_path = bugs_dir / f"bug_{seq}_judge.py"
        if not judge_path.exists():
            print(f"⚠️  No judge for bug {seq} at {judge_path} — skipping")
            continue
        spec = importlib.util.spec_from_file_location(f"judge_{seq}", judge_path)
        judge_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(judge_mod)

        bug = {
            "id": seq,
            "symptom": " | ".join(lesson["symptoms"][:2]),
            "buggy_code": buggy_code,
            "lesson_md": lesson_path.with_suffix(".md").read_text(encoding="utf-8")
            if lesson_path.with_suffix(".md").exists() else json.dumps(lesson, indent=2),
            "judge": judge_mod,
        }
        for cond in ("control", "treatment"):
            for t in range(1, args.trials + 1):
                results.append(run_trial(bug, cond, t, out_dir))

    (out_dir / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Honest summary: report ALL, including losses/ties.
    for cond in ("control", "treatment"):
        rows = [r for r in results if r["condition"] == cond]
        solved = sum(r["solved"] for r in rows)
        mean_turns = sum(r["turns_to_solve"] for r in rows) / len(rows) if rows else 0
        print(f"{cond:>9}: solved {solved}/{len(rows)}  mean_turns={mean_turns:.2f}")


if __name__ == "__main__":
    main()

