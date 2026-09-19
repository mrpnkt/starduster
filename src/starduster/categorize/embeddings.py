"""Stored repo embeddings (`data/embeddings.npz`).

Each repo is embedded once. Vectors are kept unit-length, so cosine similarity
is a dot product. The model digest is stored alongside: vectors from two
different model builds live in different spaces and must never be mixed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from ..models import Repo
from .npz import load_npz, save_npz


class EmbeddingError(RuntimeError):
    pass


def _normalize(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    if m.size == 0:
        return m
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1.0, norms)


@dataclass(frozen=True, eq=False)
class EmbeddingSet:
    names: tuple[str, ...]
    vectors: np.ndarray  # (n, dim) float32, unit rows
    digest: str
    probe: np.ndarray | None = None  # reference vectors for PROBE_TEXTS

    def missing(self, repos: Sequence[Repo]) -> tuple[Repo, ...]:
        have = set(self.names)
        return tuple(r for r in repos if r.full_name not in have)

    def vector(self, name: str) -> np.ndarray | None:
        try:
            return self.vectors[self.names.index(name)]
        except ValueError:
            return None

    def with_added(
        self, names: Sequence[str], vectors: np.ndarray, digest: str | None = None
    ) -> "EmbeddingSet":
        if digest is not None and self.digest and digest != self.digest:
            raise EmbeddingError(
                f"Embedding model digest changed ({self.digest[:12]} -> {digest[:12]}). "
                "Mixing vectors from different model builds is meaningless; "
                "re-embed everything with `starduster embed --rebuild`."
            )
        if not len(names):
            return self
        stacked = _normalize(vectors) if not len(self.names) else np.vstack([self.vectors, _normalize(vectors)])
        return EmbeddingSet(self.names + tuple(names), stacked, digest or self.digest, self.probe)

    def with_probe(self, probe: np.ndarray) -> "EmbeddingSet":
        return EmbeddingSet(self.names, self.vectors, self.digest, _normalize(probe))


def empty(digest: str = "") -> EmbeddingSet:
    return EmbeddingSet((), np.zeros((0, 0), dtype=np.float32), digest)


def save_embeddings(path: str | Path, es: EmbeddingSet) -> Path:
    arrays = {
        "names": np.array(es.names, dtype=str),
        # float16 halves the committed file; cosine error is ~1e-3, far below
        # the category margins that matter.
        "vectors": es.vectors.astype(np.float16),
        "digest": np.array(es.digest),
    }
    if es.probe is not None:
        arrays["probe"] = es.probe.astype(np.float32)
    return save_npz(path, compress=False, **arrays)


def load_embeddings(path: str | Path) -> EmbeddingSet:
    data = load_npz(path)
    if data is None:
        return empty()
    return EmbeddingSet(
        names=tuple(str(n) for n in data["names"]),
        vectors=_normalize(data["vectors"].astype(np.float32)),
        digest=str(data["digest"]),
        probe=data.get("probe"),
    )
