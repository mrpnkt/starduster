"""Failure ledger: bounded retries, so no repo is retried (and billed) daily.

A repo the model refuses, answers unparseably, or that errors in a batch is
recorded here. After `MAX_ATTEMPTS_PER_REPO` attempts under the same prompt
and taxonomy version it is skipped until one of those versions changes (or,
with REPROCESS_ON_CONTENT_CHANGE, until the repo's content changes).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Mapping

from ..config import MAX_ATTEMPTS_PER_REPO
from ..models import Repo


@dataclass(frozen=True, slots=True)
class Failure:
    full_name: str
    input_hash: str
    version_key: str
    attempts: int


def is_exhausted(
    failure: Failure | None,
    version_key: str,
    current_hash: str,
    reprocess_on_change: bool,
    max_attempts: int = MAX_ATTEMPTS_PER_REPO,
) -> bool:
    if failure is None or failure.version_key != version_key:
        return False
    if reprocess_on_change and failure.input_hash != current_hash:
        return False
    return failure.attempts >= max_attempts


def record_attempts(
    ledger: Mapping[str, Failure],
    attempted: Iterable[Repo],
    succeeded: set[str],
    version_key: str,
    hash_of: Callable[[Repo], str],
) -> dict[str, Failure]:
    """Return a new ledger: successes cleared, failures incremented."""
    out = dict(ledger)
    for repo in attempted:
        name = repo.full_name
        if name in succeeded:
            out.pop(name, None)
            continue
        prior = out.get(name)
        same_version = prior is not None and prior.version_key == version_key
        out[name] = Failure(
            full_name=name,
            input_hash=hash_of(repo),
            version_key=version_key,
            attempts=(prior.attempts + 1) if same_version else 1,
        )
    return out


def ledger_to_dict(ledger: Mapping[str, Failure]) -> dict[str, Any]:
    return {
        f.full_name: {"input_hash": f.input_hash, "version_key": f.version_key, "attempts": f.attempts}
        for f in ledger.values()
    }


def ledger_from_dict(raw: Mapping[str, Any]) -> dict[str, Failure]:
    return {
        name: Failure(name, d.get("input_hash", ""), d.get("version_key", ""), int(d.get("attempts", 0)))
        for name, d in raw.items()
        if isinstance(d, Mapping)
    }
