"""Pure mapping from GraphQL response nodes to `Repo` values.

Kept free of network and I/O so the awkward shapes GitHub actually returns —
null languages, null licenses, absent descriptions, inaccessible repos that
come back as null nodes — are all covered by fast unit tests.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from ..models import Repo
from .readme import prepare_readme, redact_secrets


def _topics(node: Mapping[str, Any]) -> tuple[str, ...]:
    raw = (node.get("repositoryTopics") or {}).get("nodes") or []
    names = {
        (entry.get("topic") or {}).get("name")
        for entry in raw
        if isinstance(entry, Mapping)
    }
    return tuple(sorted(n for n in names if n))


def pick_readme(node: Mapping[str, Any]) -> str:
    """Return the first non-empty README blob among the aliased fields.

    README filenames vary, so the query asks for several aliases named
    `readme_0`, `readme_1`, ... in preference order. A Blob for a binary or
    LFS-backed file carries no usable `text`.
    """
    aliases = sorted(k for k in node if k.startswith("readme_"))
    for alias in aliases:
        blob = node.get(alias)
        if not isinstance(blob, Mapping):
            continue
        text = blob.get("text")
        if isinstance(text, str) and text.strip():
            return text
    return ""


def normalize_edge(edge: Mapping[str, Any]) -> Repo:
    """Map one `starredRepositories` edge to a `Repo`."""
    node = edge["node"]
    readme = prepare_readme(pick_readme(node))
    return Repo(
        full_name=node["nameWithOwner"],
        description=redact_secrets(node.get("description") or ""),
        topics=_topics(node),
        stars=node.get("stargazerCount") or 0,
        language=(node.get("primaryLanguage") or {}).get("name"),
        license=(node.get("licenseInfo") or {}).get("spdxId"),
        pushed_at=node.get("pushedAt") or "",
        starred_at=edge.get("starredAt") or "",
        is_archived=bool(node.get("isArchived")),
        is_fork=bool(node.get("isFork")),
        url=node.get("url") or f"https://github.com/{node['nameWithOwner']}",
        readme_excerpt=readme,
    )


def normalize_edges(edges: Iterable[Mapping[str, Any]]) -> tuple[Repo, ...]:
    """Map many edges, skipping nulls and de-duplicating by full name.

    GitHub returns a null `node` for repos that have since become private or
    were deleted; those must not abort a 3,267-repo fetch.
    """
    seen: dict[str, Repo] = {}
    for edge in edges:
        if not edge or not edge.get("node"):
            continue
        repo = normalize_edge(edge)
        seen.setdefault(repo.full_name, repo)
    return tuple(seen.values())
