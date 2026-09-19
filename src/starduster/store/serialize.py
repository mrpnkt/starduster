"""Domain objects <-> the JSON shapes committed under `data/`."""

from __future__ import annotations

from typing import Any, Mapping

from ..models import Repo, Summary


def repo_to_dict(repo: Repo) -> dict[str, Any]:
    return {
        "full_name": repo.full_name,
        "description": repo.description,
        "topics": list(repo.topics),
        "stars": repo.stars,
        "language": repo.language,
        "license": repo.license,
        "pushed_at": repo.pushed_at,
        "starred_at": repo.starred_at,
        "is_archived": repo.is_archived,
        "is_fork": repo.is_fork,
        "url": repo.url,
        "readme_excerpt": repo.readme_excerpt,
    }


def repo_from_dict(data: Mapping[str, Any]) -> Repo:
    return Repo(
        full_name=data["full_name"],
        description=data.get("description") or "",
        topics=tuple(data.get("topics") or ()),
        stars=data.get("stars") or 0,
        language=data.get("language"),
        license=data.get("license"),
        pushed_at=data.get("pushed_at") or "",
        starred_at=data.get("starred_at") or "",
        is_archived=bool(data.get("is_archived")),
        is_fork=bool(data.get("is_fork")),
        url=data.get("url") or "",
        readme_excerpt=data.get("readme_excerpt") or "",
    )


def summaries_to_dict(items: Mapping[str, Summary]) -> dict[str, Any]:
    return {
        s.full_name: {
            "summary": s.summary,
            "labels": list(s.labels),
            "input_hash": s.input_hash,
            "model": s.model,
            "version_key": s.version_key,
        }
        for s in items.values()
    }


def summaries_from_dict(raw: Mapping[str, Any]) -> dict[str, Summary]:
    return {
        name: Summary(
            full_name=name,
            summary=d.get("summary") or "",
            labels=tuple(d.get("labels") or ()),
            input_hash=d.get("input_hash") or "",
            model=d.get("model") or "",
            version_key=d.get("version_key") or "",
        )
        for name, d in raw.items()
    }
