"""Tests for the Docker-free logic of the Lore verifier.

The runner's docker invocation itself needs a real Docker daemon (smoke
tests in smoke.py); everything decidable without Docker is decided
here, including the pipeline's negative-first short-circuit — tested by
monkeypatching run_eval with scripted outputs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from lore.asserts import EvalOutput, all_passed, evaluate_assertion
from lore.builder import context_hash, generate_dockerfile
from lore.static_checks import check_duplicate_keys
from lore import runner as runner_mod
from lore.runner import _write_files, verify_lesson


WD = Path("/tmp/lore-test-wd")


def out(exit_code=0, stdout="", stderr="", timed_out=False):
    return EvalOutput(exit_code, stdout, stderr, 0.1, timed_out)


# ---------------- asserts engine ----------------

def test_exit_code_pass_and_fail():
    a = {"type": "exit_code", "equals": 0}
    assert evaluate_assertion(a, out(0), WD).passed
    assert not evaluate_assertion(a, out(1), WD).passed


def test_stderr_contains_and_not_contains():
    o = out(0, stderr="Unclosed client session\n")
    assert evaluate_assertion({"type": "stderr_contains", "value": "Unclosed client session"}, o, WD).passed
    assert not evaluate_assertion({"type": "stderr_not_contains", "value": "Unclosed client session"}, o, WD).passed
    assert evaluate_assertion({"type": "stderr_not_contains", "value": "Event loop is closed"}, o, WD).passed


def test_timeout_fails_every_assertion():
    o = out(0, stdout="SUCCESS", timed_out=True)
    assert not evaluate_assertion({"type": "stdout_contains", "value": "SUCCESS"}, o, WD).passed


def test_unknown_assertion_type_fails_not_skips():
    assert not evaluate_assertion({"type": "vibes"}, out(0), WD).passed


def test_file_asserts_and_traversal_guard(tmp_path):
    (tmp_path / "result.txt").write_text("hello lore")
    assert evaluate_assertion({"type": "file_exists", "path": "result.txt"}, out(), tmp_path).passed
    assert evaluate_assertion({"type": "file_contains", "path": "result.txt", "value": "lore"}, out(), tmp_path).passed
    assert not evaluate_assertion({"type": "file_contains", "path": "result.txt", "value": "absent"}, out(), tmp_path).passed
    # traversal refused
    assert not evaluate_assertion({"type": "file_exists", "path": "../../etc/passwd"}, out(), tmp_path).passed


def test_all_passed_requires_nonempty():
    assert not all_passed([])  # zero assertions is never a pass


# ---------------- builder ----------------

def test_context_hash_stable_and_sensitive():
    h1 = context_hash("python:3.12-slim", ["pip install aiohttp"], "packages")
    h2 = context_hash("python:3.12-slim", ["pip install aiohttp"], "packages")
    h3 = context_hash("python:3.12-slim", ["pip install aiohttp==3.9"], "packages")
    h4 = context_hash("python:3.12-slim", ["pip install aiohttp"], "none")
    assert h1 == h2
    assert h1 != h3 and h1 != h4


def test_generate_dockerfile():
    df = generate_dockerfile("python:3.12-slim", ["pip install 'aiohttp>=3.9,<4.0'"])
    assert df.splitlines()[0] == "FROM python:3.12-slim"
    assert "RUN pip install 'aiohttp>=3.9,<4.0'" in df
    assert "WORKDIR /work" in df


# ---------------- runner file writing ----------------

def test_write_files_refuses_traversal(tmp_path):
    with pytest.raises(ValueError):
        _write_files(tmp_path, {"../escape.py": "print('no')"})


def test_write_files_nested_ok(tmp_path):
    _write_files(tmp_path, {"pkg/mod.py": "x = 1"})
    assert (tmp_path / "pkg" / "mod.py").read_text() == "x = 1"


# ---------------- pipeline: negative-first short-circuit ----------------

class FakeImage:
    tag = "lore-verify:deadbeef"
    image_id = "sha256:fake"
    cached = True


def lesson_fixture(**overrides):
    v = {
        "run": "python test_fix.py",
        "files": {"test_fix.py": "print('SUCCESS')"},
        "asserts": [{"type": "stdout_contains", "value": "SUCCESS"}],
        "must_fail_without_fix": True,
        "broken_files": {"test_broken.py": "import sys; ..."},
        "broken_run": "python test_broken.py",
        "broken_asserts": [{"type": "stderr_contains", "value": "DECLARED SYMPTOM"}],
        "timeout_sec": 30,
        "network": "none",
    }
    v.update(overrides)
    return {"id": "lore:x/y/0001", "semver": "1.0.0", "verification": v}


def scripted_run_eval(script):
    """Return a run_eval double that pops scripted outputs and logs calls."""
    calls = []

    def fake(image_tag, files, command, timeout_sec, network="none"):
        calls.append(command)
        o = script.pop(0)
        wd = Path("/tmp") / f"fake-{len(calls)}"
        wd.mkdir(parents=True, exist_ok=True)
        return o, wd

    return fake, calls


def test_placebo_negative_blocks_positive(monkeypatch):
    """THE v0.2 REGRESSION TEST: broken variant fails (exit 1) but without
    the declared symptom -> negative run rejected -> fix NEVER runs."""
    script = [out(exit_code=1, stderr="some unrelated crash")]
    fake, calls = scripted_run_eval(script)
    monkeypatch.setattr(runner_mod, "run_eval", fake)

    report = verify_lesson(lesson_fixture(), FakeImage())
    assert report.verdict == "fail"
    assert [v.variant for v in report.variants] == ["negative"]
    assert calls == ["python test_broken.py"]  # positive was never executed


def test_symptomatic_negative_then_passing_positive(monkeypatch):
    script = [
        out(exit_code=1, stderr="DECLARED SYMPTOM observed"),
        out(exit_code=0, stdout="SUCCESS"),
    ]
    fake, calls = scripted_run_eval(script)
    monkeypatch.setattr(runner_mod, "run_eval", fake)

    report = verify_lesson(lesson_fixture(), FakeImage())
    assert report.verdict == "pass"
    assert [v.variant for v in report.variants] == ["negative", "positive"]


def test_exit_zero_failure_mode(monkeypatch):
    """The aiohttp case: broken variant exits 0; symptom on stderr is the evidence."""
    lesson = lesson_fixture(
        broken_asserts=[
            {"type": "exit_code", "equals": 0},
            {"type": "stderr_contains", "value": "Unclosed client session"},
        ]
    )
    script = [
        out(exit_code=0, stderr="Unclosed client session\n"),
        out(exit_code=0, stdout="SUCCESS"),
    ]
    fake, _ = scripted_run_eval(script)
    monkeypatch.setattr(runner_mod, "run_eval", fake)
    assert verify_lesson(lesson, FakeImage()).verdict == "pass"


def test_missing_broken_asserts_is_hard_error(monkeypatch):
    fake, _ = scripted_run_eval([out()])
    monkeypatch.setattr(runner_mod, "run_eval", fake)
    with pytest.raises(runner_mod.RunnerError):
        verify_lesson(lesson_fixture(broken_asserts=[]), FakeImage())


def test_no_negative_when_must_fail_false(monkeypatch):
    script = [out(exit_code=0, stdout="SUCCESS")]
    fake, calls = scripted_run_eval(script)
    monkeypatch.setattr(runner_mod, "run_eval", fake)

    report = verify_lesson(lesson_fixture(must_fail_without_fix=False), FakeImage())
    assert report.verdict == "pass"
    assert [v.variant for v in report.variants] == ["positive"]
    assert calls == ["python test_fix.py"]


# ---------------- duplicate key static check ----------------

def test_duplicate_key_check_rejects_duplicates():
    valid_json = '{"a": 1, "b": 2}'
    dupe_json = '{"a": 1, "a": 2}'
    assert check_duplicate_keys(valid_json).passed
    res = check_duplicate_keys(dupe_json)
    assert not res.passed
    assert "duplicate key detected" in res.detail

