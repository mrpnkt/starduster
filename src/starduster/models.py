"""Immutable domain types.

Every type here is a frozen dataclass: transformations return new objects
rather than mutating existing ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class Repo:
    """A starred repository as fetched from GitHub."""

    full_name: str  # "owner/name" — the stable primary key
    description: str
    topics: tuple[str, ...]
    stars: int
    language: str | None
    license: str | None
    pushed_at: str  # ISO-8601 UTC
    starred_at: str  # ISO-8601 UTC — when *this user* starred it
    is_archived: bool
    is_fork: bool
    url: str
    readme_excerpt: str = ""

    @property
    def owner(self) -> str:
        return self.full_name.split("/", 1)[0]

    @property
    def name(self) -> str:
        return self.full_name.split("/", 1)[-1]

    def with_readme(self, excerpt: str) -> "Repo":
        """Return a copy carrying a README excerpt."""
        return replace(self, readme_excerpt=excerpt)


@dataclass(frozen=True, slots=True)
class Summary:
    """Pass A output: what a repo actually is, read from its README."""

    full_name: str
    summary: str
    labels: tuple[str, ...]
    input_hash: str
    model: str
    version_key: str = ""  # prompt version that produced it; see cache.py


@dataclass(frozen=True, slots=True)
class Classification:
    """Where a repo sits in the taxonomy: its nearest category centre.

    Computed at build time from embeddings, never stored: the same embedding
    and taxonomy always give the same answer, so there is nothing to redo.
    `primary` is None when no category is close enough ("unsorted").
    """

    full_name: str
    primary: str | None
    secondary: tuple[str, ...]
    similarity: float


@dataclass(frozen=True, slots=True)
class Category:
    """One leaf of the taxonomy."""

    id: str
    name: str
    definition: str
    parent: str
    disambiguation: str = ""
    # Repos whose mean embedding defines this category's centre. Lets you add
    # or split a category by hand; overrides the clustered centre if present.
    seeds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Group:
    """A top-level grouping of categories."""

    id: str
    name: str


@dataclass(frozen=True, slots=True)
class Taxonomy:
    """The category tree. Categories are assigned from embeddings at build
    time, so editing names or grouping never requires reprocessing anything."""

    version: str
    groups: tuple[Group, ...]
    categories: tuple[Category, ...]
    # Hand-set categories for individual repos ("owner/name" -> category id).
    pins: Mapping[str, str] = field(default_factory=dict)

    @property
    def leaf_ids(self) -> tuple[str, ...]:
        return tuple(c.id for c in self.categories)

    def category(self, category_id: str) -> Category | None:
        return next((c for c in self.categories if c.id == category_id), None)

    def children_of(self, group_id: str) -> tuple[Category, ...]:
        return tuple(c for c in self.categories if c.parent == group_id)


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """A repo joined with everything known about it, ready for the site."""

    repo: Repo
    summary: Summary | None
    classification: Classification | None
