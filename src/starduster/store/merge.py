"""Pure joins and delta selection.

Kept free of I/O and fully unit-tested. The rule for LLM summaries: each repo
is summarized once. Redoing needs a deliberate PROMPT_VERSION bump, and
failures are retried a bounded number of times (see failures.py), never daily.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from .keys import summary_hash, summary_version_key
from ..config import REPROCESS_ON_CONTENT_CHANGE
from .failures import Failure, is_exhausted
from ..models import CatalogEntry, Classification, Repo, Summary


def _needs_work(
    repo: Repo,
    existing_hash: str | None,
    existing_version: str | None,
    current_hash: str,
    version_key: str,
    failures: Mapping[str, Failure],
    reprocess_on_change: bool,
) -> bool:
    if existing_hash is None:
        needed = True  # never processed
    elif existing_version != version_key:
        needed = True  # deliberate prompt/taxonomy version bump
    else:
        needed = reprocess_on_change and existing_hash != current_hash
    if not needed:
        return False
    return not is_exhausted(
        failures.get(repo.full_name), version_key, current_hash, reprocess_on_change
    )


def repos_needing_summary(
    repos: Sequence[Repo],
    cached: Mapping[str, Summary],
    prompt_version: str,
    *,
    failures: Mapping[str, Failure] | None = None,
    reprocess_on_change: bool = REPROCESS_ON_CONTENT_CHANGE,
) -> tuple[Repo, ...]:
    """Repos that still need a Pass A summary.

    By default a repo is summarized once: edits to its description or topics
    do not trigger a new (billed) summary, only a PROMPT_VERSION bump does.
    """
    key = summary_version_key(prompt_version)
    out = []
    for r in repos:
        existing = cached.get(r.full_name)
        if _needs_work(
            r,
            existing.input_hash if existing else None,
            existing.version_key if existing else None,
            summary_hash(r, prompt_version),
            key,
            failures or {},
            reprocess_on_change,
        ):
            out.append(r)
    return tuple(out)


def build_catalog(
    repos: Sequence[Repo],
    summaries: Mapping[str, Summary],
    classifications: Mapping[str, Classification],
) -> tuple[CatalogEntry, ...]:
    """Join repos with their summaries and classifications.

    Ordered most-recently-starred first, which is the default the site shows.
    Missing summaries/classifications are tolerated so a partially classified
    corpus still renders.
    """
    entries = tuple(
        CatalogEntry(
            repo=r,
            summary=summaries.get(r.full_name),
            classification=classifications.get(r.full_name),
        )
        for r in repos
    )
    return tuple(sorted(entries, key=lambda e: e.repo.starred_at, reverse=True))
