"""SqliteLessonStore — persistent lesson storage with confidence-weighted retrieval.

Same architectural pattern as SqliteEpisodeStore (SQLite, cosine search,
L2-normalized vectors), but with:
- Hierarchical fast-path retrieval:
    * Tier 1: exact task_id match + GLOBAL scope (<1ms)
    * Tier 2: task_family match + DOMAIN scope (<5ms)
    * Tier 3: cosine embedding search with guard filtering (<20ms)
- Confidence-weighted ranking: ``score = relevance × bayesian_confidence``
- Model-specific gating and untested model policy (``inject_untested`` flag)
- Negative guard indexing and O(1) set-based suppression
- ``update_confidence(lesson_id, helped, harmed, model)`` for the verification loop
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
    LessonScope,
    LessonType,
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
        "times_harmed": getattr(lesson, "times_harmed", 0),
        "model_confidence": getattr(lesson, "model_confidence", {}),
        "scope": lesson.scope.value if hasattr(lesson.scope, "value") else str(getattr(lesson, "scope", "specific")),
        "lesson_type": lesson.lesson_type.value if hasattr(lesson.lesson_type, "value") else str(getattr(lesson, "lesson_type", "positive")),
        "parent_lesson_id": getattr(lesson, "parent_lesson_id", ""),
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

    raw_scope = d.get("scope", "specific")
    try:
        scope = LessonScope(raw_scope)
    except ValueError:
        scope = LessonScope.SPECIFIC

    raw_type = d.get("lesson_type", "positive")
    try:
        lesson_type = LessonType(raw_type)
    except ValueError:
        lesson_type = LessonType.POSITIVE

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
        times_harmed=d.get("times_harmed", 0),
        model_confidence=d.get("model_confidence", {}),
        scope=scope,
        lesson_type=lesson_type,
        parent_lesson_id=d.get("parent_lesson_id", ""),
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


def _get_lesson_confidence(
    lesson: Lesson,
    *,
    model: str = "",
    inject_untested: bool = True,
) -> float:
    """Evaluate confidence for a specific model under untested-model policy.

    If model is given and tracked, return model_confidence[model].
    If model is untested:
      - if inject_untested is False -> 0.0 (strict gating)
      - if inject_untested is True -> global bayesian confidence
    """
    if model:
        if model in lesson.model_confidence:
            return lesson.model_confidence[model]
        if not inject_untested:
            return 0.0
    return lesson.bayesian_confidence()


DEFAULT_VECTOR_DIM: int = 256


# --------------------------------------------------------------------------- #
# SqliteLessonStore
# --------------------------------------------------------------------------- #

class SqliteLessonStore:
    """SQLite-backed lesson storage with cosine search, hierarchical lookup,
    sqlite-vec ANN acceleration, and causal negative-guard suppression.

    Thread-safety: one connection per store instance, same as SqliteEpisodeStore.
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        *,
        dim: int = DEFAULT_VECTOR_DIM,
        use_vec: bool = True,
    ) -> None:
        self.db_path = db_path
        self.dim = dim
        self.use_vec = use_vec
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if self.use_vec:
            self._try_load_vec()
        self._create_tables()

    def _try_load_vec(self) -> None:
        try:
            import sqlite_vec
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)
        except Exception:
            self.use_vec = False

    def _create_tables(self) -> None:
        self._conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS lessons (
                id               TEXT PRIMARY KEY,
                task_id          TEXT NOT NULL DEFAULT '',
                task_family      TEXT NOT NULL DEFAULT '',
                confidence       REAL NOT NULL DEFAULT 0.5,
                times_applied    INTEGER NOT NULL DEFAULT 0,
                times_helped     INTEGER NOT NULL DEFAULT 0,
                scope            TEXT NOT NULL DEFAULT 'specific',
                lesson_type      TEXT NOT NULL DEFAULT 'positive',
                parent_lesson_id TEXT NOT NULL DEFAULT '',
                created_at       TEXT NOT NULL,
                vector           BLOB NOT NULL,
                payload          TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_lessons_task ON lessons(task_id);
            CREATE INDEX IF NOT EXISTS ix_lessons_family ON lessons(task_family);
            CREATE INDEX IF NOT EXISTS ix_lessons_confidence ON lessons(confidence);
            CREATE INDEX IF NOT EXISTS ix_lessons_parent ON lessons(parent_lesson_id);
            CREATE INDEX IF NOT EXISTS ix_lessons_scope ON lessons(scope);
            CREATE INDEX IF NOT EXISTS ix_lessons_type ON lessons(lesson_type);
            """
        )
        # Migrations in case table was created with older schema
        for col_def in (
            "scope TEXT NOT NULL DEFAULT 'specific'",
            "lesson_type TEXT NOT NULL DEFAULT 'positive'",
            "parent_lesson_id TEXT NOT NULL DEFAULT ''",
        ):
            try:
                self._conn.execute(f"ALTER TABLE lessons ADD COLUMN {col_def}")
            except sqlite3.OperationalError:
                pass

        if self.use_vec:
            try:
                self._conn.execute(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS lesson_vectors USING vec0("
                    f"lesson_id TEXT, "
                    f"embedding float[{self.dim}] distance_metric=cosine"
                    f");"
                )
            except sqlite3.OperationalError:
                self.use_vec = False

        self._conn.commit()

    # --- write path --------------------------------------------------------

    def add(self, lesson: Lesson, vector: Vector) -> None:
        """Store or update a lesson with its embedding vector.

        Idempotent: same lesson.id = update (INSERT OR REPLACE).
        """
        if len(vector) != self.dim:
            raise ValueError(f"vector dim {len(vector)} != store dim {self.dim}")
        
        scope_str = lesson.scope.value if hasattr(lesson.scope, "value") else str(lesson.scope)
        type_str = lesson.lesson_type.value if hasattr(lesson.lesson_type, "value") else str(lesson.lesson_type)

        self._conn.execute(
            "INSERT OR REPLACE INTO lessons "
            "(id, task_id, task_family, confidence, times_applied, times_helped, "
            "scope, lesson_type, parent_lesson_id, created_at, vector, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                lesson.id,
                lesson.task_id,
                lesson.task_family,
                lesson.bayesian_confidence(),
                lesson.times_applied,
                lesson.times_helped,
                scope_str,
                type_str,
                lesson.parent_lesson_id,
                lesson.created_at.isoformat() if isinstance(lesson.created_at, datetime) else str(lesson.created_at),
                _pack(vector),
                json.dumps(_lesson_to_dict(lesson), ensure_ascii=False),
            ),
        )

        if self.use_vec:
            try:
                self._conn.execute("DELETE FROM lesson_vectors WHERE lesson_id = ?", (lesson.id,))
                self._conn.execute(
                    "INSERT INTO lesson_vectors(lesson_id, embedding) VALUES (?, ?)",
                    (lesson.id, _pack(vector)),
                )
            except sqlite3.OperationalError:
                pass

        self._conn.commit()

    def update_confidence(
        self, lesson_id: str, *, helped: bool, harmed: bool = False, model: str = ""
    ) -> None:
        """Update confidence counters after a lesson is applied.

        Tracks whether it helped or harmed, updating global and per-model
        Bayesian posteriors.
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
        if harmed:
            lesson.times_harmed += 1

        if model:
            lesson.update_model_confidence(model, helped=helped, harmed=harmed)

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

    # --- guard methods -----------------------------------------------------

    def get_guards_for_parent(self, parent_lesson_id: str) -> list[Lesson]:
        """Return all negative guard lessons associated with a parent lesson."""
        rows = self._conn.execute(
            "SELECT payload FROM lessons WHERE parent_lesson_id = ? AND lesson_type = 'negative'",
            (parent_lesson_id,),
        ).fetchall()
        return [_dict_to_lesson(json.loads(r["payload"])) for r in rows]

    def get_active_guards(
        self,
        parent_lesson_ids: Collection[str],
        *,
        model: str = "",
    ) -> set[str]:
        """Return set of parent_lesson_ids that are actively blocked for model.

        Uses indexed parent lookup for O(1) set matching.
        """
        if not parent_lesson_ids:
            return set()
        
        placeholders = ",".join("?" for _ in parent_lesson_ids)
        rows = self._conn.execute(
            f"SELECT payload FROM lessons WHERE parent_lesson_id IN ({placeholders}) AND lesson_type = 'negative'",
            list(parent_lesson_ids),
        ).fetchall()

        blocked: set[str] = set()
        for r in rows:
            guard = _dict_to_lesson(json.loads(r["payload"]))
            if not model:
                blocked.add(guard.parent_lesson_id)
            elif not guard.model_confidence or model in guard.model_confidence:
                blocked.add(guard.parent_lesson_id)
        return blocked

    # --- hierarchical fast-path queries -----------------------------------

    def get_by_task_id(
        self,
        task_id: str,
        *,
        model: str = "",
        min_confidence: float = 0.0,
        inject_untested: bool = True,
        include_global: bool = True,
    ) -> list[Lesson]:
        """Tier 1 lookup: exact task_id match and/or GLOBAL scoped lessons."""
        query = (
            "SELECT payload FROM lessons WHERE "
            "(task_id = ? OR (scope = 'global' AND ? = 1)) "
            "AND lesson_type != 'negative'"
        )
        rows = self._conn.execute(query, (task_id, 1 if include_global else 0)).fetchall()
        candidates = [_dict_to_lesson(json.loads(r["payload"])) for r in rows]
        if not candidates:
            return []

        active_guards = self.get_active_guards([c.id for c in candidates], model=model)
        valid: list[Lesson] = []
        for c in candidates:
            if c.id in active_guards:
                continue
            conf = _get_lesson_confidence(c, model=model, inject_untested=inject_untested)
            if conf >= min_confidence:
                valid.append(c)
        return valid

    def get_by_task_family(
        self,
        task_family: str,
        *,
        model: str = "",
        min_confidence: float = 0.0,
        inject_untested: bool = True,
        include_domain: bool = True,
    ) -> list[Lesson]:
        """Tier 2 lookup: exact task_family match and/or DOMAIN scoped lessons."""
        query = (
            "SELECT payload FROM lessons WHERE "
            "(task_family = ? OR (scope = 'domain' AND ? = 1)) "
            "AND lesson_type != 'negative'"
        )
        rows = self._conn.execute(query, (task_family, 1 if include_domain else 0)).fetchall()
        candidates = [_dict_to_lesson(json.loads(r["payload"])) for r in rows]
        if not candidates:
            return []

        active_guards = self.get_active_guards([c.id for c in candidates], model=model)
        valid: list[Lesson] = []
        for c in candidates:
            if c.id in active_guards:
                continue
            conf = _get_lesson_confidence(c, model=model, inject_untested=inject_untested)
            if conf >= min_confidence:
                valid.append(c)
        return valid

    # --- read path ---------------------------------------------------------

    def search(
        self,
        vector: Vector,
        k: int,
        *,
        exclude_ids: Collection[str] = (),
        min_confidence: float = 0.0,
        model: str = "",
        inject_untested: bool = True,
    ) -> list[RetrievedMemory]:
        """k nearest lessons by score = cosine_similarity × bayesian_confidence.

        Uses native sqlite-vec ANN vector join when available, with seamless
        fallback to Python brute-force cosine similarity.
        """
        exclude = set(exclude_ids)

        if self.use_vec:
            try:
                fetch_k = max(k * 4, 30)
                query = (
                    "SELECT l.id, l.payload, v.distance "
                    "FROM lesson_vectors v "
                    "JOIN lessons l ON v.lesson_id = l.id "
                    "WHERE v.embedding MATCH ? AND k = ? AND l.lesson_type != 'negative' "
                    "ORDER BY v.distance"
                )
                rows = self._conn.execute(query, (_pack(vector), fetch_k)).fetchall()
                if rows:
                    active_guards = self.get_active_guards([r["id"] for r in rows], model=model)
                    scored: list[tuple[float, str, float, Lesson]] = []
                    for r in rows:
                        row_id = r["id"]
                        if row_id in exclude or row_id in active_guards:
                            continue
                        lesson = _dict_to_lesson(json.loads(r["payload"]))
                        conf = _get_lesson_confidence(lesson, model=model, inject_untested=inject_untested)
                        if conf < min_confidence:
                            continue
                        relevance = max(-1.0, min(1.0, 1.0 - float(r["distance"])))
                        score = relevance * conf
                        scored.append((score, row_id, conf, lesson))

                    scored.sort(key=lambda t: t[0], reverse=True)
                    out: list[RetrievedMemory] = []
                    for score, lid, conf, lesson in scored[:k]:
                        content = _format_lesson_for_retrieval(lesson, model=model)
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
                                    "scope": lesson.scope.value,
                                },
                            )
                        )
                    return out
            except Exception:
                pass

        rows = list(self._conn.execute(
            "SELECT id, vector, confidence, payload FROM lessons WHERE lesson_type != 'negative'",
        ))

        candidates: list[tuple[str, Lesson, list[float]]] = []
        for row in rows:
            row_id = row["id"]
            if row_id in exclude:
                continue
            payload = json.loads(row["payload"])
            lesson = _dict_to_lesson(payload)
            candidates.append((row_id, lesson, _unpack(row["vector"])))

        if not candidates:
            return []

        active_guards = self.get_active_guards([c[0] for c in candidates], model=model)

        scored: list[tuple[float, str, float, Lesson]] = []
        for row_id, lesson, vec in candidates:
            if row_id in active_guards:
                continue

            conf = _get_lesson_confidence(lesson, model=model, inject_untested=inject_untested)
            if conf < min_confidence:
                continue

            relevance = _cosine(vector, vec)
            score = relevance * conf
            scored.append((score, row_id, conf, lesson))

        scored.sort(key=lambda t: t[0], reverse=True)

        out: list[RetrievedMemory] = []
        for score, lid, conf, lesson in scored[:k]:
            content = _format_lesson_for_retrieval(lesson, model=model)
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
                        "scope": lesson.scope.value,
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

def _format_lesson_for_retrieval(lesson: Lesson, model: str = "") -> str:
    """Format a lesson into a compact, actionable prompt injection.

    Lessons are ~100 tokens vs ~500+ for raw episodes — the 5x compression
    that makes consolidation pay for itself in token efficiency.
    """
    parts = []

    header = []
    if lesson.task_family:
        header.append(lesson.task_family)
    if lesson.scope:
        header.append(f"scope:{lesson.scope.value}")
    if header:
        parts.append(f"[{' | '.join(header)}]")

    if lesson.symptom:
        parts.append(f"Symptom: {lesson.symptom}")

    if lesson.fix:
        parts.append(f"Fix: {lesson.fix}")

    if lesson.rationale:
        parts.append(f"Why: {lesson.rationale}")

    conf = lesson.bayesian_confidence(model=model)
    parts.append(f"(confidence: {conf:.2f}, verified {lesson.times_helped}/{lesson.times_applied} times)")

    return "\n".join(parts)
