"""Embedding parity check between machines.

Categories are assigned by comparing vectors made in GitHub Actions (Linux,
CPU) with centres built from vectors made on your Mac (Metal). If the two
builds of the model ever disagree, new stars would be placed in a subtly
different space. Fixed probe texts are embedded on both; if they drift, the
run stops instead of silently mis-filing repos.
"""

from __future__ import annotations

import numpy as np

PROBE_TEXTS: tuple[str, ...] = (
    "clustering: A command-line tool for searching files by content.",
    "clustering: Post-exploitation command and control framework for red teams.",
    "clustering: Self-hosted bookmark manager with a web interface.",
    "clustering: Python library for training neural networks on GPUs.",
)


class ProbeError(RuntimeError):
    pass


def check_probe(reference: np.ndarray, current: np.ndarray, min_similarity: float) -> float:
    """Return the worst probe similarity; raise if below `min_similarity`."""
    sims = np.sum(reference * current, axis=1)
    worst = float(sims.min())
    if worst < min_similarity:
        raise ProbeError(
            f"Embeddings from this machine differ from the stored ones (worst probe "
            f"cosine {worst:.4f} < {min_similarity}). The model build changed. "
            "To avoid mixing vector spaces, re-embed everything on one machine "
            "with `starduster embed --rebuild` and re-run `starduster taxonomy`."
        )
    return worst
