"""Real coding tasks: file-seeded, deterministically graded.

A ``CodingTask`` mirrors Lore's existing lesson-verification format — seed
files into a workspace, let the agent edit, then run a check command whose
exit code is the verdict. Grading is a subprocess, not an LLM judge, so the
success signal is objective.

Tasks come in *families*. Members of a family share an underlying lesson
(e.g. "asyncio.gather needs return_exceptions=True to capture failures"),
so a lesson learned on one member should transfer to another. That
relatedness is what makes learning measurable; without it there is no
transfer to observe.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..models import Outcome, OutcomeStatus

CHECK_TIMEOUT_SEC = 60


@dataclass(slots=True)
class CodingTask:
    id: str
    family: str
    prompt_text: str
    source_dir: str                      # where seed files live
    entry_files: list[str]               # files copied into the workspace
    eval_command: list[str]              # graded by exit code (0 = pass)
    is_control: bool = False
    editable: list[str] = field(default_factory=list)

    # ---- Task protocol -------------------------------------------------- #
    def prompt(self) -> str:
        return self.prompt_text

    def setup(self, workspace: str) -> None:
        for name in self.entry_files:
            src = os.path.join(self.source_dir, name)
            dst = os.path.join(workspace, name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)

    def evaluate(self, workspace: str) -> Outcome:
        try:
            proc = subprocess.run(
                self.eval_command,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=CHECK_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            return Outcome(OutcomeStatus.TIMEOUT, detail="check timed out")
        except FileNotFoundError as exc:
            # Missing interpreter/tool is an infra fault, not an agent failure.
            return Outcome(OutcomeStatus.ERROR, detail=str(exc))

        if proc.returncode == 0:
            return Outcome(OutcomeStatus.SUCCESS, score=1.0, detail=proc.stdout[-500:])
        return Outcome(
            OutcomeStatus.FAILURE,
            score=0.0,
            detail=(proc.stdout + proc.stderr)[-500:],
        )


def _try_yaml_load(path: Path) -> dict:
    """Load YAML, falling back to a simple parser if pyyaml isn't installed."""
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except ImportError:
        pass
    # Minimal fallback: parse the subset of YAML used in our task files.
    import json
    text = path.read_text(encoding="utf-8")
    # Convert our simple YAML to JSON-ish for basic parsing.
    result: dict = {}
    current_key = None
    multiline: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if current_key and multiline is not None:
                multiline.append("")
            continue
        if line[0] != " " and ":" in line:
            # Flush previous multiline
            if current_key and multiline:
                result[current_key] = "\n".join(multiline)
                multiline = []
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "|":
                current_key = key
                multiline = []
            elif val.startswith("[") and val.endswith("]"):
                result[key] = json.loads(val.replace("'", '"'))
            elif val.lower() in ("true", "false"):
                result[key] = val.lower() == "true"
            else:
                result[key] = val
                current_key = None
        elif current_key is not None:
            multiline.append(line.rstrip())
    if current_key and multiline:
        # Strip common indent from multiline block
        lines = multiline
        while lines and not lines[0].strip():
            lines = lines[1:]
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        if lines:
            indent = len(lines[0]) - len(lines[0].lstrip())
            result[current_key] = "\n".join(l[indent:] for l in lines)
    return result


def load_task(task_dir: str | Path) -> CodingTask:
    """Load one task from a directory containing ``task.yaml`` + seed files."""
    task_dir = Path(task_dir)
    spec = _try_yaml_load(task_dir / "task.yaml")
    return CodingTask(
        id=spec["id"],
        family=spec["family"],
        prompt_text=spec["prompt"],
        source_dir=str(task_dir),
        entry_files=spec["entry_files"],
        eval_command=spec["eval_command"],
        is_control=bool(spec.get("is_control", False)),
        editable=spec.get("editable", []),
    )


def load_tasks(root: str | Path) -> list[CodingTask]:
    """Recursively load every task under ``root`` (any dir with task.yaml)."""
    root = Path(root)
    tasks: list[CodingTask] = []
    for yaml_path in sorted(root.rglob("task.yaml")):
        tasks.append(load_task(yaml_path.parent))
    return tasks
