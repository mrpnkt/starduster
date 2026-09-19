"""Data paths must follow the checkout, not wherever the package is installed.

Regression: with a regular (non-editable) `pip install .`, paths derived from
`__file__` pointed into site-packages. CI then saw no stored data, refetched
every README and started re-embedding the whole corpus.
"""

import os
import subprocess
import sys
from pathlib import Path


def root_in(cwd, env_extra=None):
    env = {**os.environ, **(env_extra or {})}
    env.pop("STARDUSTER_ROOT", None) if not env_extra else None
    out = subprocess.run(
        [sys.executable, "-c", "from starduster import config; print(config.ROOT)"],
        cwd=cwd, env=env, capture_output=True, text=True, check=True,
    )
    return Path(out.stdout.strip()).resolve()


def test_root_is_the_working_directory(tmp_path):
    assert root_in(tmp_path) == tmp_path.resolve()


def test_root_can_be_overridden(tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert root_in(tmp_path, {"STARDUSTER_ROOT": str(other)}) == other.resolve()


def test_data_paths_hang_off_root(tmp_path):
    out = subprocess.run(
        [sys.executable, "-c", "from starduster import config; print(config.RAW_STARS_PATH)"],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    assert Path(out.stdout.strip()).resolve() == (tmp_path / "data" / "raw-stars.json").resolve()
