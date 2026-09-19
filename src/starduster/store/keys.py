"""Content-hash keys for LLM summaries.

A summary records a hash of exactly the inputs that produced it, and the
prompt version. Pure functions, so the rules are directly testable.
"""

from __future__ import annotations

import hashlib
import json

from ..models import Repo

_HASH_ALGO = "sha256"


def _digest(parts: object) -> str:
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.new(_HASH_ALGO, payload.encode("utf-8")).hexdigest()[:32]


def _repo_signal(repo: Repo) -> dict[str, object]:
    """The repo fields that actually influence an LLM's answer.

    Deliberately excludes star count and push date: those change constantly
    and would invalidate the cache daily without changing what the repo *is*.
    """
    return {
        "full_name": repo.full_name,
        "description": repo.description,
        "topics": sorted(repo.topics),  # order-insensitive: a reorder is not a change
        "language": repo.language,
        "readme": repo.readme_excerpt,
    }


def summary_hash(repo: Repo, prompt_version: str) -> str:
    """Content hash of what a summary was made from."""
    return _digest({"kind": "summary", "v": prompt_version, **_repo_signal(repo)})


def summary_version_key(prompt_version: str) -> str:
    """The versions a summary depends on. Changing it is a deliberate reprocess."""
    return f"prompt={prompt_version}"
