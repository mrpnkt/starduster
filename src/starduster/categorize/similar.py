"""Top-k most similar repos for every repo, for the site's "similar" view."""

from __future__ import annotations

import numpy as np

from ..config import SIMILAR_REPOS


def similar_indices(matrix: np.ndarray, k: int = SIMILAR_REPOS, chunk: int = 512) -> list[list[int]]:
    """Row indices of each row's k nearest other rows, most similar first.

    Chunked so the full n x n similarity matrix never has to exist at once.
    """
    n = matrix.shape[0]
    k = min(k, n - 1)
    if k <= 0:
        return [[] for _ in range(n)]
    out: list[list[int]] = []
    for start in range(0, n, chunk):
        sims = matrix[start : start + chunk] @ matrix.T
        for local, row in enumerate(sims):
            row = row.copy()
            row[start + local] = -np.inf  # never your own neighbour
            top = np.argpartition(-row, k)[:k]
            out.append([int(i) for i in top[np.argsort(-row[top], kind="stable")]])
    return out
