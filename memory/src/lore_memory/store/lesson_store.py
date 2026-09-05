"""SqliteLessonStore — persistent lesson storage with confidence-weighted retrieval.

Same architectural pattern as SqliteEpisodeStore (SQLite, cosine search,
L2-normalized vectors), but with:
- Confidence-weighted ranking: ``score = relevance × bayesian_confidence``
- ``update_confidence(lesson_id, helped)`` for the verification loop
- Idempotent upsert (same lesson id = update, not duplicate)
"""

from __future__ import annotations

import json
import math
import sqlite3
import struct
from collections.abc import Collection, Sequence
from datetime import datetime, timezone

from ..models import (
    Lesson,
    MemoryKind,
    RetrievedMemory,
    Vector,
    new_id,
    utcnow,
)


# --------------------------------------------------------------------------- #
# Serialisation helpers
# --------------------------------------------------------------------------- #

def _lesson_to_dict(lesson: Lesson) -> dict:
    return {
        "id": lesson.id,
        "symptom": lesson.symptom,
        "fix": lesson.fix,
        "rationale": lesson.rationale,
        "statement": lesson.statement,
        "source_episode_ids": lesson.source_episode_ids,
        "task_id": lesson.task_id,
        "task_family": lesson.task_family,
        "confidence": lesson.confidence,
        "times_applied": lesson.times_applied,
        "times_helped": lesson.times_helped,
        "tags": lesson.tags,
        "created_at": lesson.created_at.isoformat() if isinstance(lesson.created_at, datetime) else str(lesson.created_at),
        "last_used": lesson.last_used.isoformat() if isinstance(lesson.last_used, datetime) else None,
    }


def _dict_to_lesson(d: dict) -> Lesson:
    ca = d.get("created_at")
    if isinstance(ca, str):
        try:
            created_at = datetime.fromisoformat(ca)
        except ValueError:
            created_at = datetime.now(timezone.utc)
    else:
        created_at = datetime.now(timezone.utc)

    lu = d.get("last_used")
    last_used = None
    if isinstance(lu, str):
        try:
            last_used = datetime.fromisoformat(lu)
        except ValueError:
            pass

    return Lesson(
        symptom=d.get("symptom", ""),
        fix=d.get("fix", ""),
        rationale=d.get("rationale", ""),
        statement=d.get("statement", ""),
        source_episode_ids=d.get("source_episode_ids", []),
        task_id=d.get("task_id", ""),
        task_family=d.get("task_family", ""),
        confidence=d.get("confidence", 0.5),
        times_applied=d.get("times_applied", 0),
        times_helped=d.get("times_helped", 0),
        tags=d.get("tags", []),
        id=d.get("id", ""),
        created_at=created_at,
        last_used=last_used,
    )


# --------------------------------------------------------------------------- #
# Vector helpers (same as episode_store.py)
# --------------------------------------------------------------------------- #

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return max(-1.0, min(1.0, dot))


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


# --------------------------------------------------------------------------- #
# SqliteLessonStore
# --------------------------------------------------------------------------- #

class SqliteLessonStore:
    """SQLite-backed lesson storage with cosine search and confidence weighting.

    Thread-safety: one connection per store instance, same as SqliteEpisodeStore.
    """

    def __init__(self, db_path: str = ":memory:", *, dim: int = 256) -> None:
        self.db_path = db_path
        self.dim = dim
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS lessons (
                id          TEXT PRIMARY KEY,
                task_id     TEXT NOT NULL DEFAULT '',
                task_family TEXT NOT NULL DEFAULT '',
                confidence  REAL NOT NULL DEFAULT 0.5,
                times_applied INTEGER NOT NULL DEFAULT 0,
                times_helped  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL,
                vector      BLOB NOT NULL,
                payload     TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_lessons_task ON lessons(task_id);
            CREATE INDEX IF NOT EXISTS ix_lessons_family ON lessons(task_family);
            CREATE INDEX IF NOT EXISTS ix_lessons_confidence ON lessons(confidence);
            """
        )
        self._conn.commit()

    # --- write path --------------------------------------------------------

    def add(self, lesson: Lesson, vector: Vector) -> None:
        """Store or update a lesson with its embedding vector.

        Idempotent: same lesson.id = update (INSERT OR REPLACE).
        """
        if len(vector) != self.dim:
            raise ValueError(f"vector dim {len(vector)} != store dim {self.dim}")
        self._conn.execute(
            "INSERT OR REPLACE INTO lessons "
            "(id, task_id, task_family, confidence, times_applied, times_helped, "
            "created_at, vector, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                lesson.id,
                lesson.task_id,
                lesson.task_family,
                lesson.bayesian_confidence(),
                lesson.times_applied,
                lesson.times_helped,
                lesson.created_at.isoformat() if isinstance(lesson.created_at, datetime) else str(lesson.created_at),
                _pack(vector),
                json.dumps(_lesson_to_dict(lesson), ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def update_confidence(self, lesson_id: str, *, helped: bool) -> None:
        """Update confidence counters after a lesson is applied.

        This is the verification loop: each time a lesson is retrieved
        and used, we track whether it actually helped.
        """
        row = self._conn.execute(
            "SELECT payload FROM lessons WHERE id = ?", (lesson_id,)
        ).fetchone()
        if row is None:
            return

        lesson = _dict_to_lesson(json.loads(row["payload"]))
        lesson.times_applied += 1
        if helped:
            lesson.times_helped += 1
        lesson.confidence = lesson.bayesian_confidence()
        lesson.last_used = utcnow()

        self._conn.execute(
            "UPDATE lessons SET confidence = ?, times_applied = ?, "
            "times_helped = ?, payload = ? WHERE id = ?",
            (
                lesson.confidence,
                lesson.times_applied,
                lesson.times_helped,
                json.dumps(_lesson_to_dict(lesson), ensure_ascii=False),
                lesson_id,
            ),
        )
        self._conn.commit()

    # --- read path ---------------------------------------------------------

    def search(
        self,
        vector: Vector,
        k: int,
        *,
        exclude_ids: Collection[str] = (),
        min_confidence: float = 0.0,
    ) -> list[RetrievedMemory]:
        """k nearest lessons by score = cosine_similarity × bayesian_confidence.

        This is the key difference from episode search: lessons are ranked
        by proven utility, not just embedding similarity.
        """
        exclude = set(exclude_ids)
        rows = list(self._conn.execute(
            "SELECT id, vector, confidence, payload FROM lessons "
            "WHERE confidence >= ?",
            (min_confidence,),
        ))

        scored: list[tuple[float, str, float, str]] = []
        for row in rows:
            row_id = row["id"]
            if row_id in exclude:
                continue
            relevance = _cosine(vector, _unpack(row["vector"]))
            confidence = row["confidence"]
            # Combined score: relevance × confidence
            score = relevance * confidence
            scored.append((score, row_id, confidence, row["payload"]))

        scored.sort(key=lambda t: t[0], reverse=True)

        out: list[RetrievedMemory] = []
        for score, lid, conf, payload_json in scored[:k]:
            lesson = _dict_to_lesson(json.loads(payload_json))
            # Format lesson content for system prompt injection
            content = _format_lesson_for_retrieval(lesson)
            out.append(
                RetrievedMemory(
                    kind=MemoryKind.LESSON,
                    id=lid,
                    content=content,
                    score=float(score),
                    metadata={
                        "task_id": lesson.task_id,
                        "task_family": lesson.task_family,
                        "confidence": conf,
                        "times_applied": lesson.times_applied,
                        "times_helped": lesson.times_helped,
                    },
                )
            )
        return out

    def get(self, lesson_id: str) -> Lesson | None:
        row = self._conn.execute(
            "SELECT payload FROM lessons WHERE id = ?", (lesson_id,)
        ).fetchone()
        if row is None:
            return None
        return _dict_to_lesson(json.loads(row["payload"]))

    def get_all_with_vectors(self) -> list[tuple[Lesson, Vector]]:
        """Return all lessons with their vectors (for deduplication)."""
        rows = list(self._conn.execute("SELECT vector, payload FROM lessons"))
        return [
            (_dict_to_lesson(json.loads(row["payload"])), _unpack(row["vector"]))
            for row in rows
        ]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM lessons").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        self._conn.close()


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #

def _format_lesson_for_retrieval(lesson: Lesson) -> str:
    """Format a lesson into a compact, actionable prompt injection.

    Lessons are ~100 tokens vs ~500+ for raw episodes — the 5x compression
    that makes consolidation pay for itself in token efficiency.
    """
    parts = []

    if lesson.task_family:
        parts.append(f"[{lesson.task_family}]")

    if lesson.symptom:
        parts.append(f"Symptom: {lesson.symptom}")

    if lesson.fix:
        parts.append(f"Fix: {lesson.fix}")

    if lesson.rationale:
        parts.append(f"Why: {lesson.rationale}")

    conf = lesson.bayesian_confidence()
    parts.append(f"(confidence: {conf:.2f}, verified {lesson.times_helped}/{lesson.times_applied} times)")

    return "\n".join(parts)
