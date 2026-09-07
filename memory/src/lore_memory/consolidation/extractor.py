"""Pattern extraction from episode clusters — the heart of consolidation.

Diffs pass/fail trajectories within a cluster to extract actionable
lessons.  v1 is pure trajectory analysis, zero LLM cost:

1. **Tool call sequence comparison** — which tools were called in what
   order, what differed between pass and fail runs.
2. **Write-file content diffing** — line-level diffs of the code
   the agent wrote, with indentation awareness.
3. **Structural pattern detection** — identifies recurring patterns in
   successful trajectories that are absent from failures.

The output is a ``Lesson`` with the symptom/fix/rationale triple
populated from mechanical analysis of the trajectory diffs.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field

from ..models import AgentStep, Episode, Lesson, LessonScope, new_id
from .clustering import EpisodeCluster

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolCallSummary:
    """Summarised tool call from a trajectory step."""

    name: str
    path: str = ""         # file path if applicable
    content_hash: str = "" # quick fingerprint of content written


@dataclass(slots=True)
class TrajectoryFingerprint:
    """Fingerprint of a trajectory's tool call sequence and key content."""

    tool_sequence: list[str] = field(default_factory=list)
    tool_calls: list[ToolCallSummary] = field(default_factory=list)
    write_contents: dict[str, str] = field(default_factory=dict)  # path -> content
    key_thoughts: list[str] = field(default_factory=list)


def _extract_tool_name(action: str) -> str:
    """Extract tool name from 'tool_name({...})' format."""
    paren = action.find("(")
    if paren > 0:
        return action[:paren]
    return action


def _extract_write_content(action: str) -> tuple[str, str] | None:
    """Try to extract (path, content) from a write_file action string."""
    if not action.startswith("write_file("):
        return None
    try:
        import ast
        raw = action[len("write_file("):-1]
        args = ast.literal_eval(raw)
        if isinstance(args, dict) and "content" in args:
            return (args.get("path", "solution.py"), args["content"])
    except Exception:
        pass
    return None


def _fingerprint(episode: Episode) -> TrajectoryFingerprint:
    """Build a trajectory fingerprint from an episode."""
    fp = TrajectoryFingerprint()
    for step in episode.trajectory:
        tool = _extract_tool_name(step.action)
        fp.tool_sequence.append(tool)
        fp.tool_calls.append(ToolCallSummary(
            name=tool,
            path="",
            content_hash=str(hash(step.action[:200])),
        ))

        wc = _extract_write_content(step.action)
        if wc:
            path, content = wc
            fp.write_contents[path] = content
            fp.tool_calls[-1].path = path

        # Capture informative thoughts (skip trivial ones)
        if step.thought and len(step.thought.strip()) > 20:
            thought = step.thought.strip()
            skip_prefixes = (
                "i will finish", "finish the task", "the check passed",
                "now i will finish", "i'll call finish",
            )
            if not any(thought.lower().startswith(p) for p in skip_prefixes):
                fp.key_thoughts.append(thought)

    return fp


def _simple_line_diff(success_code: str, failure_code: str) -> dict:
    """Compute a simple line-level diff between success and failure code.

    Returns a dict with:
    - added: lines present in success but not in failure
    - removed: lines present in failure but not in success
    - moved: lines that appear in both but at different indentation
    """
    s_lines = success_code.strip().splitlines()
    f_lines = failure_code.strip().splitlines()

    s_stripped = {line.strip(): line for line in s_lines if line.strip()}
    f_stripped = {line.strip(): line for line in f_lines if line.strip()}

    added = []
    removed = []
    moved = []

    for stripped, original in s_stripped.items():
        if stripped not in f_stripped:
            added.append(original)
        elif f_stripped[stripped] != original:
            # Same content, different indentation → structural move
            moved.append({
                "content": stripped,
                "success_indent": len(original) - len(original.lstrip()),
                "failure_indent": len(f_stripped[stripped]) - len(f_stripped[stripped].lstrip()),
            })

    for stripped, original in f_stripped.items():
        if stripped not in s_stripped:
            removed.append(original)

    return {"added": added, "removed": removed, "moved": moved}


_CONTROL_FLOW_KEYWORDS = {
    "try:", "except", "finally:", "with ", "async with",
    "if ", "elif ", "else:", "for ", "while ",
    "return", "yield", "raise", "await ", "break", "continue",
    "assert ",
}

_RELEVANT_CALLS = (
    ".close()", ".cancel()", ".nack(", ".ack(",
    ".wait(", ".put(", ".get(", ".gather(", ".sleep(",
    "create_task(", "TaskGroup(",
)


def _is_causal_diff(diff: dict) -> tuple[bool, str]:
    """Check whether a code diff represents structural or control-flow changes.

    Filters out purely cosmetic differences (e.g. variable naming, comments,
    blank lines, cosmetic whitespace) to prevent false-positive lessons.

    Returns:
        (is_causal, reason)
    """
    # 1. Structural moves (indentation shifts) are control-flow structure changes
    if diff.get("moved"):
        return True, f"structural move found ({len(diff['moved'])} line(s) with indentation change)"

    added = diff.get("added", [])
    removed = diff.get("removed", [])

    for line in added + removed:
        stripped = line.strip()
        # Skip comments and docstrings
        if stripped.startswith(("#", '"""', "'''")):
            continue
        # Check control-flow keywords
        if any(kw in stripped for kw in _CONTROL_FLOW_KEYWORDS):
            return True, f"control-flow keyword detected: '{stripped[:50]}'"
        # Check relevant protocol / async method calls
        if any(call in stripped for call in _RELEVANT_CALLS):
            return True, f"protocol/resource call detected: '{stripped[:50]}'"

    return False, "diff contains only naming/cosmetic changes without structural or control-flow shifts"


def _extract_symptom_from_failures(failures: list[Episode]) -> str:
    """Extract the most common failure symptom from failed episodes."""
    details = []
    for ep in failures:
        if ep.outcome.detail:
            details.append(ep.outcome.detail.strip())

    if not details:
        return "Task failed without specific error detail"

    # Find the most common failure message
    counter = Counter(details)
    most_common, count = counter.most_common(1)[0]

    # Clean up the message
    if most_common.startswith("FAIL:"):
        most_common = most_common[5:].strip()
    if most_common.startswith("AssertionError:"):
        most_common = most_common[len("AssertionError:"):].strip()

    return most_common


def _extract_fix_from_diff(diff: dict, success_fp: TrajectoryFingerprint) -> str:
    """Extract a concrete fix description from the code diff."""
    parts = []

    # Structural moves are the strongest signal (e.g., "count += 1" moved out of try:)
    if diff["moved"]:
        for m in diff["moved"]:
            direction = "out" if m["success_indent"] < m["failure_indent"] else "into"
            indent_change = abs(m["success_indent"] - m["failure_indent"])
            parts.append(
                f"Move `{m['content']}` {direction} "
                f"(indent {'decreased' if direction == 'out' else 'increased'} by {indent_change} spaces)"
            )

    # Added lines in success
    if diff["added"]:
        for line in diff["added"][:3]:  # cap at 3
            parts.append(f"Add: `{line.strip()}`")

    # Removed lines (things the failure had that success didn't)
    if diff["removed"]:
        for line in diff["removed"][:3]:
            parts.append(f"Remove: `{line.strip()}`")

    if not parts:
        # Fallback: describe the tool sequence difference
        return "Apply the working solution pattern from successful episodes"

    return "; ".join(parts)


def _extract_rationale_from_thoughts(
    success_fps: list[TrajectoryFingerprint],
    failure_fps: list[TrajectoryFingerprint],
) -> str:
    """Extract rationale from the reasoning in successful trajectories.

    Looks for thoughts that appear in successes but not in failures,
    which likely contain the key insight that led to the correct fix.
    """
    success_thoughts = set()
    for fp in success_fps:
        for t in fp.key_thoughts:
            # Normalize for comparison
            success_thoughts.add(t.lower()[:100])

    failure_thoughts = set()
    for fp in failure_fps:
        for t in fp.key_thoughts:
            failure_thoughts.add(t.lower()[:100])

    # Thoughts unique to successes are the insight
    unique = success_thoughts - failure_thoughts
    if unique:
        # Pick the longest unique thought (most informative)
        best = max(unique, key=len)
        # Find the original (non-lowered) version
        for fp in success_fps:
            for t in fp.key_thoughts:
                if t.lower()[:100] == best:
                    return t[:300]

    # Fallback: use the last informative thought from the best success
    if success_fps and success_fps[0].key_thoughts:
        return success_fps[0].key_thoughts[-1][:300]

    return ""


class PatternExtractor:
    """Extracts Lesson objects from episode clusters by diffing pass/fail trajectories.

    This is the v1 extractor — pure trajectory analysis, zero LLM cost.
    It works well for structured code-fix tasks where the diff between
    a passing and failing solution IS the lesson.

    Usage::

        extractor = PatternExtractor()
        lessons = extractor.extract(cluster)
    """

    def extract(self, cluster: EpisodeCluster) -> list[Lesson]:
        """Extract lessons from a cluster with contrasting outcomes.

        Returns 0 or 1 lessons per cluster. A lesson is only produced
        if meaningful structural differences are found between pass
        and fail trajectories.
        """
        if not cluster.has_contrast:
            logger.debug(
                "Skipping cluster '%s' (scope=%s): no outcome contrast (%d pass, %d fail)",
                cluster.key, cluster.scope, len(cluster.successes), len(cluster.failures)
            )
            return []

        logger.debug(
            "Extracting patterns for cluster '%s' (scope=%s, %d pass, %d fail)",
            cluster.key, cluster.scope, len(cluster.successes), len(cluster.failures)
        )

        success_fps = [_fingerprint(ep) for ep in cluster.successes]
        failure_fps = [_fingerprint(ep) for ep in cluster.failures]

        # --- 1. Tool call sequence comparison ---
        success_sequences = Counter(
            tuple(fp.tool_sequence) for fp in success_fps
        )
        failure_sequences = Counter(
            tuple(fp.tool_sequence) for fp in failure_fps
        )

        # --- 2. Code diff analysis ---
        best_success_code = self._best_write_content(success_fps)
        best_failure_code = self._best_write_content(failure_fps)

        diff = {}
        fix_text = ""
        if best_success_code and best_failure_code:
            diff = _simple_line_diff(best_success_code, best_failure_code)
            is_causal, reason = _is_causal_diff(diff)
            if not is_causal:
                logger.info(
                    "Causal guard rejected diff for cluster '%s': %s",
                    cluster.key, reason
                )
                return []
            logger.debug(
                "Causal guard accepted diff for cluster '%s': %s",
                cluster.key, reason
            )
            fix_text = _extract_fix_from_diff(diff, success_fps[0])
        elif best_success_code:
            fix_text = "Apply the working solution pattern"

        # --- 3. Extract symptom / rationale ---
        symptom = _extract_symptom_from_failures(cluster.failures)
        rationale = _extract_rationale_from_thoughts(success_fps, failure_fps)

        # Only produce a lesson if we found something actionable
        if not fix_text and not symptom:
            logger.debug("Cluster '%s': no actionable fix or symptom identified", cluster.key)
            return []

        # Determine task metadata and explicit scope
        task_id = cluster.key if cluster.scope == "task_id" else ""
        task_family = ""
        if cluster.scope == "task_family":
            task_family = cluster.key
        elif cluster.successes:
            task_family = cluster.successes[0].task_family

        scope = LessonScope.SPECIFIC if cluster.scope == "task_id" else LessonScope.FAMILY

        # Build provenance
        source_ids = (
            [ep.id for ep in cluster.successes[:3]]
            + [ep.id for ep in cluster.failures[:3]]
        )

        # Attach the working code as part of the fix if available
        if best_success_code and len(best_success_code) < 600:
            fix_text += f"\nWorking code:\n```python\n{best_success_code.strip()}\n```"
        elif best_success_code:
            fix_text += f"\nWorking code (truncated):\n```python\n{best_success_code.strip()[:600]}\n```"

        lesson = Lesson(
            symptom=symptom,
            fix=fix_text,
            rationale=rationale,
            source_episode_ids=source_ids,
            task_id=task_id,
            task_family=task_family,
            confidence=0.5,  # starts neutral, moves with evidence
            scope=scope,
            tags=[f"auto-extracted", f"scope:{scope.value}"],
        )

        logger.info(
            "Extracted lesson %s for cluster '%s' (scope=%s, symptom='%s')",
            lesson.id, cluster.key, scope.value, symptom[:60]
        )
        return [lesson]

    def _best_write_content(
        self, fingerprints: list[TrajectoryFingerprint]
    ) -> str | None:
        """Find the most common write_file content across fingerprints.

        For code-fix tasks, the last write_file is usually the solution.
        """
        contents: list[str] = []
        for fp in fingerprints:
            if fp.write_contents:
                # Prefer solution.py, fall back to any file
                for key in ("solution.py", ""):
                    if key in fp.write_contents:
                        contents.append(fp.write_contents[key])
                        break
                else:
                    # Take the last-written file
                    last_key = list(fp.write_contents.keys())[-1]
                    contents.append(fp.write_contents[last_key])

        if not contents:
            return None

        # Return the most common content (handles seed-to-seed variance)
        counter = Counter(contents)
        return counter.most_common(1)[0][0]
