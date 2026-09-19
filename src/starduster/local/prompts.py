"""Prompts for the local LLM (Ollama): repo summaries and cluster naming."""

from __future__ import annotations

from ..config import SUMMARY_README_TOKENS
from ..models import Repo
from ..tokens import cap_tokens

# GitHub limits descriptions to 350 characters; cap anyway, since this is
# third-party data and caps are what bound the cost of a request.
DESCRIPTION_MAX_TOKENS = 150

SUMMARY_SYSTEM = """You describe open-source repositories factually.

Given a repository's metadata and README excerpt, write `summary`: ONE sentence
(max 160 characters) stating what the project is and what it is for. Write for
someone who has never heard of it. Lead with the noun ("A CLI that...", "A
Python library for..."). No marketing language, superlatives, or emoji. If the
README is in another language, summarize in English. Many repositories have no
description, so read the README rather than guessing from the name. If there is
genuinely not enough information, say so plainly."""


def render_repo(repo: Repo, *, include_readme: bool = True) -> str:
    """Render one repo as prompt input."""
    lines = [
        f"Repository: {repo.full_name}",
        f"Description: {cap_tokens(repo.description, DESCRIPTION_MAX_TOKENS) or '(none)'}",
        f"Topics: {', '.join(repo.topics) if repo.topics else '(none)'}",
        f"Primary language: {repo.language or '(none detected)'}",
    ]
    if include_readme and repo.readme_excerpt:
        lines.append("")
        lines.append("README excerpt:")
        # Already capped at fetch time; re-capped here so no stored data can
        # ever exceed the limit.
        lines.append(cap_tokens(repo.readme_excerpt, SUMMARY_README_TOKENS))
    elif include_readme:
        lines.append("")
        lines.append("README excerpt: (none available)")
    return "\n".join(lines)


def cluster_naming_prompt(
    examples: list[Repo], *, keywords: list[str] = (), taken: list[str] = ()
) -> str:
    """Prompt to name one cluster.

    Most of a star list can share one broad theme, so the model is given what
    makes THIS cluster different (distinctive keywords) and the names already
    used, to avoid five clusters all called "Penetration Testing Tools".
    """
    listing = "\n".join(
        f"- {r.full_name}: {cap_tokens(r.description, 60) or '(no description)'}"
        for r in examples
    )
    parts = [
        "These GitHub repositories were grouped together because they are about "
        "similar things. Name the group: a short, SPECIFIC category name (2-4 "
        "words, Title Case) and a one-sentence definition of what belongs in it. "
        "Describe what the projects are FOR, not their programming language.",
    ]
    if keywords:
        parts.append("Words that distinguish this group from all the others: "
                     + ", ".join(keywords) + ". Base the name on these.")
    if taken:
        parts.append("These names are already used by other groups; choose a "
                     "different, more specific name: " + "; ".join(taken) + ".")
    return "\n\n".join(parts + [listing])


def grouping_prompt(categories: list[tuple[str, str]]) -> str:
    listing = "\n".join(f"- {cid}: {name}" for cid, name in categories)
    return (
        "Organise these categories into 4-8 broad groups for a sidebar. Every "
        "category id must appear in exactly one group. Give each group a short "
        "Title Case name.\n\n" + listing
    )
