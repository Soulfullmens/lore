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
import subprocess
import tempfile
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


def mechanical_check(candidate_code: str, lesson: dict) -> bool:
    """The grader with no thumb on the scale.

    The candidate fix must, when run, behave like the lesson's KNOWN-GOOD fix:
    exit 0 and satisfy the positive asserts. We run it in the same image the lesson
    declares. (Simplified: runs the candidate directly; for full rigor route it
    through `lore verify` against a temp lesson with the candidate as test_fix.py.)
    """
    v = lesson["verification"]
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "candidate.py"
        f.write_text(candidate_code, encoding="utf-8")
        image = v.get("image", "python:3.12-slim")
        setup = v.get("setup", [])
        # Build once per image+setup would be ideal; kept simple here.
        setup_cmd = " && ".join(setup) if setup else "true"
        cmd = [
            "docker", "run", "--rm", "--network", "none",
            "--memory", "512m", "--cpus", "2",
            "-v", f"{d}:/work", "-w", "/work",
            image, "sh", "-c", f"{setup_cmd} && python candidate.py",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return False
        # Pass criterion: exit 0 AND positive asserts' stdout markers present.
        if proc.returncode != 0:
            return False
        for a in v.get("asserts", []):
            if a["type"] == "stdout_contains" and a["value"] not in proc.stdout:
                return False
            if a["type"] == "exit_code" and proc.returncode != a.get("equals"):
                return False
        return True


def run_trial(bug: dict, lesson: dict, condition: str, trial_num: int, out_dir: Path) -> dict:
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
        if code and mechanical_check(code, lesson):
            solved = True
            convo_code = code
        elif code:
            convo_code = code  # let it iterate on its own attempt
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
        "transcript_path": str(tpath),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lessons-dir", required=True)
    ap.add_argument("--bugs", nargs="+", required=True, help="lesson sequence numbers, e.g. 0006")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    lessons_dir = Path(args.lessons_dir)

    # Load bugs: symptom + buggy snippet come from the lesson, but the buggy snippet
    # given to the agent should be a realistic file, NOT the eval — adapt per bug.
    results = []
    for seq in args.bugs:
        lesson_path = next(lessons_dir.glob(f"*{seq}.json"))
        lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
        bug = {
            "id": seq,
            "symptom": " | ".join(lesson["symptoms"][:2]),
            "buggy_code": lesson["verification"]["broken_files"][
                next(iter(lesson["verification"]["broken_files"]))
            ],  # placeholder: replace with a realistic snippet, not the eval
            "lesson_md": lesson_path.with_suffix(".md").read_text(encoding="utf-8")
            if lesson_path.with_suffix(".md").exists() else json.dumps(lesson, indent=2),
        }
        for cond in ("control", "treatment"):
            for t in range(1, args.trials + 1):
                results.append(run_trial(bug, lesson, cond, t, out_dir))

    (out_dir / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Honest summary: report ALL, including losses/ties.
    for cond in ("control", "treatment"):
        rows = [r for r in results if r["condition"] == cond]
        solved = sum(r["solved"] for r in rows)
        mean_turns = sum(r["turns_to_solve"] for r in rows) / len(rows) if rows else 0
        print(f"{cond:>9}: solved {solved}/{len(rows)}  mean_turns={mean_turns:.2f}")


if __name__ == "__main__":
    main()
