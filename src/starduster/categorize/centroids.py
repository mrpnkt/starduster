"""Category centres (`data/centroids.npz`), produced by `starduster taxonomy`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .npz import load_npz, save_npz


@dataclass(frozen=True, eq=False)
class Centroids:
    taxonomy_version: str  # the taxonomy these were clustered for (informational)
    ids: tuple[str, ...]
    vectors: np.ndarray  # (k, dim) float32, unit rows

    def vector(self, category_id: str) -> np.ndarray | None:
        try:
            return self.vectors[self.ids.index(category_id)]
        except ValueError:
            return None


def save_centroids(path: str | Path, c: Centroids) -> Path:
    return save_npz(path, ids=np.array(c.ids, dtype=str), vectors=c.vectors.astype(np.float32),
                    taxonomy_version=np.array(c.taxonomy_version))


def load_centroids(path: str | Path) -> Centroids | None:
    data = load_npz(path)
    if data is None:
        return None
    return Centroids(str(data["taxonomy_version"]), tuple(str(i) for i in data["ids"]),
                     data["vectors"].astype(np.float32))


def recentre(old: Centroids, assignments: dict[str, str | None], es) -> Centroids:
    """New centres = mean of each category's members' (new) vectors.

    Used after re-embedding everything (e.g. a changed text recipe): the
    taxonomy and every hand edit survive, only the geometry is refreshed. A
    category with no members keeps its previous centre.
    """
    rows = []
    for category_id, previous in zip(old.ids, old.vectors):
        members = [es.vector(n) for n, c in assignments.items() if c == category_id]
        members = [v for v in members if v is not None]
        centre = np.mean(members, axis=0) if members else previous
        rows.append(centre / (np.linalg.norm(centre) or 1.0))
    return Centroids(old.taxonomy_version, old.ids, np.stack(rows).astype(np.float32))
