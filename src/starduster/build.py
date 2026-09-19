"""Emit the static site payload.

Derived facets are computed here, not in the browser, so the client ships no
date arithmetic and the buckets stay consistent with the Python tests.

READMEs are deliberately excluded from the payload: they exist only as prompt
input. Including them would multiply the page weight for no reader benefit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .config import (
    MAINTENANCE_ACTIVE_DAYS,
    MAINTENANCE_STALE_DAYS,
    STAR_BUCKETS,
)
from .taxonomy import taxonomy_to_dict
from .models import CatalogEntry, Repo, Taxonomy


def _parse(iso: str) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def maintenance_bucket(repo: Repo, now_iso: str) -> str:
    """Classify a repo's liveness.

    61% of this collection is archived or dormant past two years, so this is a
    primary navigation facet rather than a detail.
    """
    if repo.is_archived:
        return "archived"

    pushed = _parse(repo.pushed_at)
    now = _parse(now_iso)
    if pushed is None or now is None:
        return "unknown"

    age_days = (now - pushed).days
    if age_days < MAINTENANCE_ACTIVE_DAYS:
        return "active"
    if age_days < MAINTENANCE_STALE_DAYS:
        return "stale"
    return "dormant"


def star_bucket(stars: int) -> str:
    """Bucket a star count. `STAR_BUCKETS` is ordered high to low."""
    for label, floor in STAR_BUCKETS:
        if stars >= floor:
            return label
    return STAR_BUCKETS[-1][0]


def to_record(entry: CatalogEntry, now_iso: str) -> dict[str, Any]:
    """Flatten one catalog entry into the compact shape the client consumes."""
    repo = entry.repo
    summary = entry.summary
    classification = entry.classification

    return {
        "name": repo.full_name,
        "description": repo.description,
        "summary": summary.summary if summary else "",
        "labels": list(summary.labels) if summary else [],
        "topics": list(repo.topics),
        "category": classification.primary if classification else None,
        "secondary": list(classification.secondary) if classification else [],
        "language": repo.language,
        "stars": repo.stars,
        "stars_bucket": star_bucket(repo.stars),
        "maintenance": maintenance_bucket(repo, now_iso),
        "pushed": repo.pushed_at[:10],
        "starred": repo.starred_at[:10],
        "starred_year": repo.starred_at[:4],
    }


def build_payload(
    entries: Sequence[CatalogEntry],
    taxonomy: Taxonomy,
    *,
    similar: Mapping[str, Sequence[str]] | None = None,
    suggested: Mapping[str, Sequence[str]] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Assemble `web/data/repos.json`.

    `similar` maps a repo to its nearest repos by name; in the payload these
    become indices into `repos`, which is far smaller than repeating names.
    """
    now_iso = now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    index = {e.repo.full_name: i for i, e in enumerate(entries)}
    records = [
        {
            **to_record(e, now_iso),
            "similar": [index[n] for n in (similar or {}).get(e.repo.full_name, ()) if n in index],
            "suggested_topics": list((suggested or {}).get(e.repo.full_name, ())),
        }
        for e in entries
    ]

    return {
        "meta": {
            "generated_at": now_iso,
            "total": len(records),
            "unclassified": sum(1 for r in records if r["category"] is None),
            "untagged": sum(1 for r in records if not r["topics"]),
            "suggested": sum(1 for r in records if r["suggested_topics"]),
            "unsummarized": sum(1 for r in records if not r["summary"]),
        },
        "taxonomy": taxonomy_to_dict(taxonomy),
        "repos": records,
    }
