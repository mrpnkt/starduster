"""Taxonomy parsing, validation and serialization.

`data/taxonomy.json` is edited by hand: rename categories, rewrite their
definitions, move them between groups, or delete one (its repos then fall to
their nearest remaining category). That makes strict validation essential: an
orphaned category would silently vanish from the sidebar, and a duplicate id
would silently merge two categories.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .models import Category, Group, Taxonomy


class TaxonomyError(ValueError):
    """The taxonomy file is malformed in a way that would corrupt browsing."""


def _require_unique(ids: Sequence[str], kind: str) -> None:
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise TaxonomyError(f"Duplicate {kind} ids: {dupes}")


def _parse_category(raw: Mapping[str, Any]) -> Category:
    cat_id = str(raw.get("id") or "").strip()
    if not cat_id:
        raise TaxonomyError(f"Category with blank id: {raw!r}")
    if cat_id.startswith("__"):
        raise TaxonomyError(
            f"Category id `{cat_id}`: ids starting with `__` are reserved by the site"
        )
    return Category(
        id=cat_id,
        name=str(raw.get("name") or cat_id),
        definition=str(raw.get("definition") or ""),
        parent=str(raw.get("parent") or ""),
        disambiguation=str(raw.get("disambiguation") or ""),
        seeds=tuple(str(s) for s in raw.get("seeds") or ()),
    )


def parse_taxonomy(data: Any, *, strict: bool = False) -> Taxonomy:
    """Validate and freeze a taxonomy mapping.

    `strict` additionally rejects groups that contain no categories, which is
    useful right after a bootstrap but too harsh for hand-edited files where a
    group may be temporarily empty.
    """
    if not isinstance(data, Mapping):
        raise TaxonomyError(f"Taxonomy must be an object, got {type(data).__name__}")

    version = data.get("version")
    if not version or not isinstance(version, str):
        raise TaxonomyError("Taxonomy needs a non-empty string `version`")
    if not data.get("categories"):
        raise TaxonomyError("Taxonomy has no categories")

    groups = tuple(
        Group(id=str(g["id"]), name=str(g.get("name") or g["id"]))
        for g in data.get("groups") or []
    )
    categories = tuple(_parse_category(raw) for raw in data["categories"])
    _require_unique([g.id for g in groups], "group")
    _require_unique([c.id for c in categories], "category")

    known = {g.id for g in groups}
    for category in categories:
        if category.parent not in known:
            raise TaxonomyError(
                f"Category `{category.id}` has unknown parent "
                f"`{category.parent}` (known groups: {sorted(known)})"
            )

    pins = {str(k): str(v) for k, v in (data.get("pins") or {}).items()}
    unknown = sorted({v for v in pins.values()} - {c.id for c in categories})
    if unknown:
        raise TaxonomyError(f"`pins` point at unknown category ids: {unknown}")

    taxonomy = Taxonomy(version=version, groups=groups, categories=categories, pins=pins)
    if strict:
        empty = [g.id for g in groups if not taxonomy.children_of(g.id)]
        if empty:
            raise TaxonomyError(f"Groups with no categories: {empty}")
    return taxonomy


def taxonomy_to_dict(taxonomy: Taxonomy) -> dict[str, Any]:
    """Serialize a taxonomy back to its on-disk shape."""
    return {
        "version": taxonomy.version,
        "groups": [{"id": g.id, "name": g.name} for g in taxonomy.groups],
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "parent": c.parent,
                "definition": c.definition,
                "disambiguation": c.disambiguation,
                **({"seeds": list(c.seeds)} if c.seeds else {}),
            }
            for c in taxonomy.categories
        ],
        **({"pins": dict(sorted(taxonomy.pins.items()))} if taxonomy.pins else {}),
    }
