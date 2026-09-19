"""Atomic .npz writes (same guarantees as store.io for JSON)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np


def save_npz(path: str | Path, *, compress: bool = True, **arrays: np.ndarray) -> Path:
    """Write arrays atomically.

    `compress=False` for files committed daily: new rows are appended to an
    otherwise identical file, which git stores as a tiny delta. A compressed
    file changes throughout and would add a full new blob to history each day.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            (np.savez_compressed if compress else np.savez)(fh, **arrays)
        os.chmod(tmp, 0o644)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return p


def load_npz(path: str | Path) -> dict[str, np.ndarray] | None:
    try:
        with np.load(Path(path), allow_pickle=False) as data:
            return {k: data[k] for k in data.files}
    except FileNotFoundError:
        return None
