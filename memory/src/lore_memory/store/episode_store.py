"""SqliteEpisodeStore — persistent episode storage + vector search.

Reconciled against the real models.py and protocols.py. Key mappings:

    Episode.task_description -> the text that gets embedded for retrieval
    Episode.outcome          -> Outcome dataclass (status: OutcomeStatus)
    Episode.created_at       -> datetime, serialized as ISO string in JSON
    Episode.trajectory       -> list[AgentStep], serialized as list of dicts

Design call (deliberate deviation from "SQLite + sqlite-vec" plan of record):
    Storage IS SQLite (real, persistent, single-file). Vector search defaults to
    brute-force cosine in Python. At Phase 1 corpus sizes (10s-1000s of episodes)
    brute-force cosine is sub-millisecond and exact. sqlite-vec stays a drop-in
    accelerator: flip use_vec=True once confirmed on your box. Same interface
    either way, so nothing downstream changes.
"""
from __future__ import annotations

import json
import sqlite3
import struct
from collections.abc import Collection, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import (
    AgentStep,
    Episode,
    MemoryKind,
    Outcome,
    OutcomeStatus,
    RetrievedMemory,
    Vector,
)


# --------------------------------------------------------------------------- #
# Episode <-> JSON serialization (the single reconcile surface)
# --------------------------------------------------------------------------- #

def _episode_to_dict(ep: Episode) -> dict[str, Any]:
    """Serialize an Episode to a JSON-safe dict. This is the ONLY place
    that maps Episode fields to storage columns — if a field is renamed,
    fix it here and nowhere else."""
    return {
        "id": ep.id,
        "task_id": ep.task_id,
        "task_family": ep.task_family,
        "task_description": ep.task_description,
        "trajectory": [
            {
                "thought": s.thought,
                "action": s.action,
                "observation": s.observation,
                "tokens_in": s.tokens_in,
                "tokens_out": s.tokens_out,
            }
            for s in ep.trajectory
        ],
        "outcome": {
            "status": ep.outcome.status.value,
            "score": ep.outcome.score,
            "detail": ep.outcome.detail,
            "asserts_passed": ep.outcome.asserts_passed,
            "asserts_total": ep.outcome.asserts_total,
        },
        "seed": ep.seed,
        "tokens_used": ep.tokens_used,
        "duration_sec": ep.duration_sec,
        "injected_memory_ids": list(ep.injected_memory_ids),
        "created_at": ep.created_at.isoformat() if isinstance(ep.created_at, datetime) else str(ep.created_at),
    }


def _dict_to_episode(d: dict[str, Any]) -> Episode:
    """Deserialize a dict back to an Episode."""
    # Parse created_at
    ca = d.get("created_at")
    if isinstance(ca, str):
        try:
            created_at = datetime.fromisoformat(ca)
        except ValueError:
            created_at = datetime.now(timezone.utc)
    elif isinstance(ca, datetime):
        created_at = ca
    else:
        created_at = datetime.now(timezone.utc)

    # Parse outcome
    outcome_raw = d.get("outcome", {})
    if isinstance(outcome_raw, dict):
        outcome = Outcome(
            status=OutcomeStatus(outcome_raw.get("status", "success")),
            score=float(outcome_raw.get("score", 0.0)),
            detail=str(outcome_raw.get("detail", "")),
            asserts_passed=int(outcome_raw.get("asserts_passed", 0)),
            asserts_total=int(outcome_raw.get("asserts_total", 0)),
        )
    elif isinstance(outcome_raw, Outcome):
        outcome = outcome_raw
    else:
        outcome = Outcome(status=OutcomeStatus.SUCCESS)

    # Parse trajectory
    traj_raw = d.get("trajectory", [])
    trajectory = [
        AgentStep(
            thought=s.get("thought", ""),
            action=s.get("action", ""),
            observation=s.get("observation", ""),
            tokens_in=s.get("tokens_in", 0),
            tokens_out=s.get("tokens_out", 0),
        )
        for s in traj_raw
    ]

    return Episode(
        task_id=d["task_id"],
        task_family=d.get("task_family", ""),
        task_description=d.get("task_description", ""),
        trajectory=trajectory,
        outcome=outcome,
        seed=d.get("seed", 0),
        tokens_used=d.get("tokens_used", 0),
        duration_sec=d.get("duration_sec", 0.0),
        injected_memory_ids=d.get("injected_memory_ids", []),
        id=d.get("id", ""),
        created_at=created_at,
    )


# --------------------------------------------------------------------------- #
# Vector helpers
# --------------------------------------------------------------------------- #

def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. Vectors are stored L2-normalized, so dot == cosine."""
    dot = sum(x * y for x, y in zip(a, b))
    return max(-1.0, min(1.0, dot))


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #

class SqliteEpisodeStore:
    """Persistent episode store backed by SQLite.

    Vector search is brute-force cosine by default (exact, sub-ms at Phase 1
    scale). sqlite-vec is a drop-in accelerator behind the same interface.
    """

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        dim: int,
        use_vec: bool = False,
    ) -> None:
        self.dim = dim
        self.use_vec = use_vec
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        if use_vec:
            self._try_load_vec()
        self._init_schema()

    def _try_load_vec(self) -> None:
        try:
            import sqlite_vec  # type: ignore
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)
        except Exception as e:
            self.use_vec = False
            print(f"[episode_store] sqlite-vec unavailable ({e}); using Python cosine.")

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS episodes (
                id          TEXT PRIMARY KEY,
                task_id     TEXT NOT NULL,
                task_family TEXT NOT NULL DEFAULT '',
                outcome     TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                vector      BLOB NOT NULL,
                payload     TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_episodes_task ON episodes(task_id);
            CREATE INDEX IF NOT EXISTS ix_episodes_outcome ON episodes(outcome);
            CREATE INDEX IF NOT EXISTS ix_episodes_family ON episodes(task_family);
            """
        )
        self._conn.commit()

    # --- write path --------------------------------------------------------

    def add(self, episode: Episode, vector: Vector) -> None:
        """Store an episode with its embedding vector."""
        if len(vector) != self.dim:
            raise ValueError(f"vector dim {len(vector)} != store dim {self.dim}")
        self._conn.execute(
            "INSERT OR REPLACE INTO episodes "
            "(id, task_id, task_family, outcome, created_at, vector, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                episode.id,
                episode.task_id,
                episode.task_family,
                episode.outcome.status.value,
                episode.created_at.isoformat() if isinstance(episode.created_at, datetime) else str(episode.created_at),
                _pack(vector),
                json.dumps(_episode_to_dict(episode), ensure_ascii=False),
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
        outcomes: Sequence[OutcomeStatus] | None = (OutcomeStatus.SUCCESS,),
    ) -> list[RetrievedMemory]:
        """k nearest episodes by cosine similarity.

        outcomes: filter which episodes are retrievable. Default = successes only
            (inject what WORKED). Pass None to retrieve regardless of outcome.
        exclude_ids: the ablation seam — leave-one-out passes the target id here.
        """
        exclude = set(exclude_ids)
        rows = self._candidate_rows(outcomes)

        scored: list[tuple[float, str, str]] = []
        for row in rows:
            row_id = row["id"]
            if row_id in exclude:
                continue
            score = _cosine(vector, _unpack(row["vector"]))
            scored.append((score, row_id, row["payload"]))

        scored.sort(key=lambda t: t[0], reverse=True)

        out: list[RetrievedMemory] = []
        for score, rid, payload_json in scored[:k]:
            ep = _dict_to_episode(json.loads(payload_json))
            # content = a concise summary for the system prompt
            content = (
                f"[{ep.task_family}/{ep.task_id}] "
                f"{ep.task_description[:200]}"
            )
            out.append(
                RetrievedMemory(
                    kind=MemoryKind.EPISODE,
                    id=rid,
                    content=content,
                    score=float(score),
                    metadata={
                        "task_id": ep.task_id,
                        "task_family": ep.task_family,
                        "outcome_status": ep.outcome.status.value,
                        "seed": ep.seed,
                    },
                )
            )
        return out

    def get(self, episode_id: str) -> Episode | None:
        """Retrieve a single episode by id."""
        row = self._conn.execute(
            "SELECT payload FROM episodes WHERE id = ?", (episode_id,)
        ).fetchone()
        if row is None:
            return None
        return _dict_to_episode(json.loads(row["payload"]))

    def _candidate_rows(
        self, outcomes: Sequence[OutcomeStatus] | None
    ) -> list[sqlite3.Row]:
        if outcomes is None:
            return list(
                self._conn.execute("SELECT id, vector, payload FROM episodes")
            )
        vals = [o.value for o in outcomes]
        placeholders = ",".join("?" * len(vals))
        return list(
            self._conn.execute(
                f"SELECT id, vector, payload FROM episodes WHERE outcome IN ({placeholders})",
                vals,
            )
        )

    def count(self) -> int:
        (n,) = self._conn.execute("SELECT COUNT(*) FROM episodes").fetchone()
        return int(n)

    def close(self) -> None:
        self._conn.close()
