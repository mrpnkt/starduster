"""The text that represents a repo in embedding space."""

from __future__ import annotations

from ..config import EMBED_PREFIX, EMBED_README_TOKENS
from ..models import Repo
from ..tokens import cap_tokens

_DESCRIPTION_TOKENS = 150


def embedding_text(repo: Repo) -> str:
    parts = [
        f"{EMBED_PREFIX}{repo.full_name}",
        cap_tokens(repo.description, _DESCRIPTION_TOKENS),
        f"Topics: {', '.join(repo.topics)}" if repo.topics else "",
        cap_tokens(repo.readme_excerpt, EMBED_README_TOKENS),
    ]
    return "\n".join(p for p in parts if p)
