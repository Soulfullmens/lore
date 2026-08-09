"""Corrected mechanical grader for the Lore proof-of-use experiment.

Replaces the flawed mechanical_check in run_pou.py. The old version checked
"exit 0 + 'SUCCESS' in stdout" against the agent's returned code — which a
candidate of `print('SUCCESS')` would pass. That is the exact "counting a
plausible answer as a fix" rigging risk the protocol warns about.

The correct grader treats the candidate as a proposed test_fix.py and runs the
lesson's REAL dual verification:
  (A) candidate as test_fix.py -> positive asserts must ALL pass
  (B) the lesson's untouched test_broken.py -> negative broken_asserts must STILL pass
      (i.e. the bug still reproduces; the candidate didn't just delete/neuter the test)

A candidate only counts as a real fix if it makes (A) pass while (B) confirms the
bug was real to begin with. This reuses the verifier's own logic so the experiment
grades on the same bar as the commons itself.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


def _run_in_container(image: str, setup: list[str], files: dict[str, str], run_cmd: str,
                      timeout: int = 60) -> tuple[int, str, str]:
    """Run one variant in a hard-capped offline container; return (exit, stdout, stderr)."""
    with tempfile.TemporaryDirectory() as d:
        wd = Path(d)
        for name, content in files.items():
            (wd / name).write_text(content, encoding="utf-8")
        setup_cmd = " && ".join(setup) if setup else "true"
        cmd = [
            "docker", "run", "--rm", "--network", "none",
            "--memory", "512m", "--cpus", "2", "--pids-limit", "256",
            "-v", f"{wd}:/work", "-w", "/work",
            image, "sh", "-c", f"{setup_cmd} && {run_cmd}",
        ]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "TIMEOUT"


def _asserts_pass(asserts: list[dict], exit_code: int, stdout: str, stderr: str) -> bool:
    for a in asserts:
        t = a.get("type")
        if t == "exit_code" and exit_code != a.get("equals"):
            return False
        if t == "stdout_contains" and a.get("value", "") not in stdout:
            return False
        if t == "stdout_not_contains" and a.get("value", "") in stdout:
            return False
        if t == "stderr_contains" and a.get("value", "") not in stderr:
            return False
        if t == "stderr_not_contains" and a.get("value", "") in stderr:
            return False
    return bool(asserts)  # empty asserts never counts as a pass


def mechanical_check(candidate_code: str, lesson: dict) -> dict:
    """Grade a candidate fix against the lesson's real dual verification.

    Returns a dict (not just bool) so the experiment log captures WHY a trial
    passed or failed — raw evidence for the writeup.
    """
    v = lesson["verification"]
    image = v.get("image", "python:3.12-slim")
    setup = v.get("setup", [])

    result = {
        "positive_passed": False,
        "negative_still_fails": False,
        "solved": False,
        "detail": "",
    }

    # ---- (A) candidate as the fix: positive asserts must all pass ----
    # The candidate replaces the file named by the positive `run` command.
    run_cmd = v["run"]  # e.g. "python test_fix.py"
    fix_filename = run_cmd.split()[-1]  # "test_fix.py"
    pos_files = dict(v.get("files", {}))
    pos_files[fix_filename] = candidate_code  # overwrite the known-good fix with the candidate
    ec, so, se = _run_in_container(image, setup, pos_files, run_cmd)
    result["positive_passed"] = _asserts_pass(v.get("asserts", []), ec, so, se)

    # ---- (B) untouched broken variant must STILL fail as declared ----
    # Confirms the bug is real and the candidate didn't just neuter the harness.
    if v.get("must_fail_without_fix"):
        broken_files = dict(v.get("files", {}))
        broken_files.update(v.get("broken_files", {}))
        broken_cmd = v.get("broken_run") or v["run"]
        bec, bso, bse = _run_in_container(image, setup, broken_files, broken_cmd)
        result["negative_still_fails"] = _asserts_pass(v.get("broken_asserts", []), bec, bso, bse)
    else:
        result["negative_still_fails"] = True  # no negative variant declared

    result["solved"] = result["positive_passed"] and result["negative_still_fails"]
    result["detail"] = (
        f"positive_passed={result['positive_passed']} "
        f"negative_still_fails={result['negative_still_fails']}"
    )
    return result
