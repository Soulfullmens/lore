"""Assertion engine for Lore verification runs.

Pure functions: (assertion, captured output) -> result. No I/O except
file_exists/file_contains, which read from the host-mounted workdir.
Keeping this pure is what makes the verifier's own correctness testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvalOutput:
    """Captured result of one eval execution."""

    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    timed_out: bool


@dataclass(frozen=True)
class AssertResult:
    assertion: dict
    passed: bool
    detail: str


def evaluate_assertion(assertion: dict, output: EvalOutput, workdir: Path) -> AssertResult:
    """Evaluate a single v0.2 assertion against captured output.

    Assertion types mirror schemas/lesson.schema.json exactly. An unknown
    type is a FAILED assertion, never a skipped one — silent skips are how
    placebo evidence sneaks back in.
    """
    atype = assertion.get("type")

    if output.timed_out:
        return AssertResult(assertion, False, "eval timed out before assertions could hold")

    if atype == "exit_code":
        expected = assertion.get("equals")
        ok = output.exit_code == expected
        return AssertResult(
            assertion, ok, f"exit_code={output.exit_code}, expected {expected}"
        )

    if atype in ("stdout_contains", "stdout_not_contains",
                 "stderr_contains", "stderr_not_contains"):
        value = assertion.get("value", "")
        stream_name = "stdout" if atype.startswith("stdout") else "stderr"
        stream = output.stdout if stream_name == "stdout" else output.stderr
        found = value in stream
        want_present = atype.endswith("_contains") and not atype.endswith("not_contains")
        ok = found if want_present else not found
        verb = "found" if found else "not found"
        return AssertResult(assertion, ok, f"{value!r} {verb} in {stream_name}")

    if atype == "file_exists":
        rel = assertion.get("path", "")
        target = _safe_join(workdir, rel)
        if target is None:
            return AssertResult(assertion, False, f"path escapes workdir: {rel!r}")
        ok = target.exists()
        return AssertResult(assertion, ok, f"{rel!r} {'exists' if ok else 'missing'}")

    if atype == "file_contains":
        rel = assertion.get("path", "")
        value = assertion.get("value", "")
        target = _safe_join(workdir, rel)
        if target is None:
            return AssertResult(assertion, False, f"path escapes workdir: {rel!r}")
        if not target.exists():
            return AssertResult(assertion, False, f"{rel!r} missing")
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return AssertResult(assertion, False, f"cannot read {rel!r}: {e}")
        ok = value in content
        return AssertResult(
            assertion, ok, f"{value!r} {'found' if ok else 'not found'} in {rel!r}"
        )

    return AssertResult(assertion, False, f"unknown assertion type: {atype!r}")


def evaluate_all(assertions: list[dict], output: EvalOutput, workdir: Path) -> list[AssertResult]:
    return [evaluate_assertion(a, output, workdir) for a in assertions]


def all_passed(results: list[AssertResult]) -> bool:
    return bool(results) and all(r.passed for r in results)


def _safe_join(workdir: Path, rel: str) -> Path | None:
    """Join rel onto workdir, refusing traversal outside it."""
    candidate = (workdir / rel).resolve()
    try:
        candidate.relative_to(workdir.resolve())
    except ValueError:
        return None
    return candidate
