"""Eval runner and verification pipeline for Lore.

Each eval executes in a hard-capped container:
  --network none|bridge   (from lesson `network`; default none)
  --memory 512m --cpus 2 --pids-limit 256
  --cap-drop ALL --security-opt no-new-privileges
  bind-mounted host workdir at /work (lets file_* asserts read results
  after the container is gone)

Timeout is enforced from OUTSIDE the container: subprocess timeout with a
grace margin, then `docker kill` on the named container. A lesson cannot
outlive its declared timeout_sec by stalling.

Pipeline order (v0.2): NEGATIVE RUN FIRST. If the broken variant does not
exhibit its declared symptom (broken_asserts), the lesson's causality
claim is already dead and the fix is never executed.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .asserts import AssertResult, EvalOutput, all_passed, evaluate_all

OUTPUT_CAP_BYTES = 1_000_000  # per stream; protects against log bombs
KILL_GRACE_SEC = 10


class RunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class VariantReport:
    variant: str                    # "negative" | "positive"
    command: str
    output: EvalOutput
    assert_results: list[AssertResult]
    passed: bool


@dataclass(frozen=True)
class VerifyReport:
    lesson_id: str
    semver: str
    image_tag: str
    image_id: str
    image_cached: bool
    variants: list[VariantReport] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        return "pass" if self.variants and all(v.passed for v in self.variants) else "fail"


def _write_files(workdir: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        target = (workdir / name).resolve()
        target.relative_to(workdir.resolve())  # raises on traversal — refuse ../ names
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def run_eval(
    image_tag: str,
    files: dict[str, str],
    command: str,
    timeout_sec: int,
    network: str = "none",
) -> tuple[EvalOutput, Path]:
    """Execute one eval variant. Returns (output, host workdir for file asserts).

    Caller owns cleanup of the returned workdir (kept alive so file_* asserts
    can inspect artifacts the eval wrote).
    """
    workdir = Path(tempfile.mkdtemp(prefix="lore-eval-"))
    _write_files(workdir, files)

    name = f"lore-run-{uuid.uuid4().hex[:12]}"
    net = "none" if network == "none" else "bridge"
    cmd = [
        "docker", "run", "--rm",
        "--name", name,
        "--network", net,
        "--memory", "512m",
        "--cpus", "2",
        "--pids-limit", "256",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "-v", f"{workdir}:/work",
        "-w", "/work",
        image_tag,
        "sh", "-c", command,
    ]

    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_sec + KILL_GRACE_SEC,
            check=False,
        )
        exit_code = proc.returncode
        stdout = proc.stdout[:OUTPUT_CAP_BYTES].decode("utf-8", errors="replace")
        stderr = proc.stderr[:OUTPUT_CAP_BYTES].decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as e:
        timed_out = True
        subprocess.run(["docker", "kill", name], capture_output=True, check=False)
        exit_code = -1
        stdout = (e.stdout or b"")[:OUTPUT_CAP_BYTES].decode("utf-8", errors="replace")
        stderr = (e.stderr or b"")[:OUTPUT_CAP_BYTES].decode("utf-8", errors="replace")

    duration = time.monotonic() - start
    return EvalOutput(exit_code, stdout, stderr, duration, timed_out), workdir


def verify_lesson(lesson: dict, built_image) -> VerifyReport:
    """Run the v0.2 verification pipeline for one lesson against a built image.

    Static checks (schema, budgets, injection lint) are assumed to have
    passed BEFORE this is called — this function only proves/refutes the
    lesson's behavioral claims.
    """
    v = lesson["verification"]
    timeout = int(v.get("timeout_sec", 120))
    network = v.get("network", "none")
    must_fail = bool(v.get("must_fail_without_fix", False))

    variants: list[VariantReport] = []
    tempdirs: list[Path] = []

    try:
        # ---- NEGATIVE FIRST ----
        if must_fail:
            broken_files = dict(v.get("files", {}))
            broken_files.update(v.get("broken_files", {}))  # broken overrides/extends
            broken_cmd = v.get("broken_run") or v["run"]
            broken_asserts = v.get("broken_asserts", [])
            if not broken_asserts:
                raise RunnerError(
                    "must_fail_without_fix is true but broken_asserts is empty — "
                    "v0.2 forbids symptom-free negative runs (placebo evidence)"
                )
            out, wd = run_eval(built_image.tag, broken_files, broken_cmd, timeout, network)
            tempdirs.append(wd)
            results = evaluate_all(broken_asserts, out, wd)
            neg = VariantReport("negative", broken_cmd, out, results, all_passed(results))
            variants.append(neg)
            if not neg.passed:
                # Causality claim refuted; do not run the fix.
                return VerifyReport(
                    lesson["id"], lesson["semver"],
                    built_image.tag, built_image.image_id, built_image.cached,
                    variants,
                )

        # ---- POSITIVE ----
        out, wd = run_eval(built_image.tag, dict(v.get("files", {})), v["run"], timeout, network)
        tempdirs.append(wd)
        results = evaluate_all(v.get("asserts", []), out, wd)
        variants.append(VariantReport("positive", v["run"], out, results, all_passed(results)))

        return VerifyReport(
            lesson["id"], lesson["semver"],
            built_image.tag, built_image.image_id, built_image.cached,
            variants,
        )
    finally:
        for d in tempdirs:
            shutil.rmtree(d, ignore_errors=True)
