"""Embedding providers for episodic retrieval.

Two implementations behind one EmbeddingProvider protocol:
  - HashEmbedder  : deterministic, zero-dependency, offline. Use in tests and
                    for the offline demo so Phase 1 is provable without quota.
                    It is NOT semantic — it hashes token trigrams into a fixed
                    vector. Good enough to prove the *plumbing* (store/retrieve/
                    ablation) and to separate identical vs unrelated task text.
  - GeminiEmbedder: real semantic embeddings via google-genai. Use for the
                    actual learning-signal runs. Only file besides llm.py that
                    touches the SDK, so SDK drift is contained here.

Both satisfy the EmbeddingProvider protocol from protocols.py:
    dim: int (property)
    embed(texts: Sequence[str]) -> list[Vector]

Note: embed() takes a Sequence[str] and returns list[Vector] (batch). For
single-text convenience, callers can do embed([text])[0].
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import Sequence

from ..models import Vector

_TOKEN = re.compile(r"[a-z0-9_]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _l2_normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    if n == 0.0:
        return v
    return [x / n for x in v]


class HashEmbedder:
    """Deterministic hashing embedder. No network, no deps. Reproducible.

    Satisfies EmbeddingProvider protocol. embed() takes a batch of texts.
    """

    def __init__(self, dim: int = 256) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _features(self, text: str):
        toks = _tokens(text)
        # unigrams + adjacent bigrams -> a little word-order sensitivity
        yield from toks
        for a, b in zip(toks, toks[1:]):
            yield f"{a}\x1f{b}"

    def _embed_one(self, text: str) -> Vector:
        vec = [0.0] * self._dim
        for feat in self._features(text):
            h = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "big") % self._dim
            sign = 1.0 if (h[4] & 1) else -1.0   # signed hashing reduces collisions
            vec[idx] += sign
        return _l2_normalize(vec)

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        return [self._embed_one(t) for t in texts]


class GeminiEmbedder:
    """Real embeddings via google-genai. Requires GEMINI_API_KEY.

    Satisfies EmbeddingProvider protocol. The exact SDK surface moves; if
    google-genai's embed call shape has shifted, this is the ONLY place to
    fix it — exactly like llm.py.

        pip install google-genai
        export GEMINI_API_KEY=...
    """

    def __init__(self, model: str = "text-embedding-004", dim: int = 768) -> None:
        self.model = model
        self._dim = dim
        self._client = None

    @property
    def dim(self) -> int:
        return self._dim

    def _lazy_client(self):
        if self._client is None:
            from google import genai  # type: ignore — imported lazily so offline paths never need it
            self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        return self._client

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        client = self._lazy_client()
        out: list[Vector] = []
        for text in texts:
            resp = client.models.embed_content(model=self.model, contents=text)
            values = list(resp.embeddings[0].values)
            out.append(_l2_normalize(values))
        return out
