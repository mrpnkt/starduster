"""Atomic, deterministic JSON persistence.

Writes go through a temp file in the same directory and an atomic rename, so an
interrupted run (or a killed CI job) can never leave a half-written data file
that the next run would read as truth.

Output is sorted and non-escaped so committed data files produce small, stable
git diffs and keep their CJK descriptions readable.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: str | Path, default: Any = None) -> Any:
    """Read JSON, returning `default` if the file is absent or corrupt.

    A truncated data file should degrade to "nothing cached yet" rather than
    crash the pipeline; the content-hash cache will simply refill it.
    """
    p = Path(path)
    try:
        with p.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, NotADirectoryError):
        return default
    except (json.JSONDecodeError, UnicodeDecodeError):
        return default


def write_json(path: str | Path, payload: Any, *, compact: bool = False) -> Path:
    """Write JSON atomically. Returns the path written."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    separators = (",", ":") if compact else None
    indent = None if compact else 2

    fd, tmp_name = tempfile.mkstemp(
        dir=str(p.parent), prefix=f".{p.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(
                payload,
                fh,
                ensure_ascii=False,
                sort_keys=True,
                indent=indent,
                separators=separators,
            )
            if not compact:
                fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, 0o644)  # mkstemp creates 0600
        os.replace(tmp_name, p)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return p
