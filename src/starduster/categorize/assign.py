"""Nearest-centre categorization. Free, deterministic, recomputed every build.

A category's centre is the mean of its `seeds` if the taxonomy lists any,
otherwise the clustered centre from `centroids.npz`. Categories deleted from
the taxonomy simply have no centre, so their repos fall to the nearest
remaining one.
"""

from __future__ import annotations

import numpy as np

from collections import defaultdict
from typing import Sequence

from ..config import NEIGHBOUR_CONSENSUS, SECONDARY_MARGIN, UNSORTED_SIMILARITY
from ..models import Classification, Taxonomy
from .centroids import Centroids
from .embeddings import EmbeddingSet


def _centres(taxonomy: Taxonomy, centroids: Centroids, es: EmbeddingSet) -> tuple[list[str], np.ndarray]:
    ids, rows = [], []
    for category in taxonomy.categories:
        seed_vectors = [v for v in (es.vector(s) for s in category.seeds) if v is not None]
        if seed_vectors:
            centre = np.mean(seed_vectors, axis=0)
        else:
            centre = centroids.vector(category.id)
        if centre is None:
            continue
        ids.append(category.id)
        rows.append(centre / (np.linalg.norm(centre) or 1.0))
    return ids, (np.stack(rows).astype(np.float32) if rows else np.zeros((0, 0), np.float32))


def categories_without_centre(taxonomy: Taxonomy, centroids: Centroids, es: EmbeddingSet) -> tuple[str, ...]:
    """Categories that can never receive repos: no clustered centre, no usable seeds."""
    have, _ = _centres(taxonomy, centroids, es)
    return tuple(c.id for c in taxonomy.categories if c.id not in have)


def assign_categories(
    es: EmbeddingSet,
    centroids: Centroids,
    taxonomy: Taxonomy,
    *,
    min_similarity: float = UNSORTED_SIMILARITY,
    secondary_margin: float = SECONDARY_MARGIN,
    neighbours: Sequence[Sequence[int]] | None = None,
    consensus: float = NEIGHBOUR_CONSENSUS,
) -> dict[str, Classification]:
    """Nearest centre per repo, then (if `neighbours` is given) a consensus
    override: see config.NEIGHBOUR_CONSENSUS."""
    ids, centres = _centres(taxonomy, centroids, es)
    if not ids or not es.names:
        return {}
    sims = es.vectors @ centres.T
    order = np.argsort(-sims, axis=1)
    out: dict[str, Classification] = {}
    for row, name in enumerate(es.names):
        first = order[row, 0]
        best = float(sims[row, first])
        primary = ids[first] if best >= min_similarity else None
        secondary: tuple[str, ...] = ()
        if primary and len(ids) > 1:
            second = order[row, 1]
            if best - float(sims[row, second]) <= secondary_margin:
                secondary = (ids[second],)
        out[name] = Classification(name, primary, secondary, round(best, 4))
    if neighbours is not None:
        out = _apply_consensus(es, out, neighbours, consensus)
    return _apply_pins(out, taxonomy)


def _apply_pins(assigned: dict[str, Classification], taxonomy: Taxonomy) -> dict[str, Classification]:
    """Hand-set categories win over everything computed."""
    return {
        name: (Classification(name, taxonomy.pins[name], (), c.similarity)
               if name in taxonomy.pins else c)
        for name, c in assigned.items()
    }


def _apply_consensus(
    es: EmbeddingSet,
    first_pass: dict[str, Classification],
    neighbours: Sequence[Sequence[int]],
    threshold: float,
) -> dict[str, Classification]:
    """Votes come from the nearest-centre labels, so overrides never cascade."""
    out = dict(first_pass)
    for row, name in enumerate(es.names):
        votes: dict[str, float] = defaultdict(float)
        for j in neighbours[row]:
            label = first_pass[es.names[j]].primary
            if label is not None:
                votes[label] += max(0.0, float(es.vectors[row] @ es.vectors[j]))
        total = sum(votes.values())
        if not total:
            continue
        winner, weight = max(votes.items(), key=lambda kv: kv[1])
        current = first_pass[name]
        if winner != current.primary and weight / total >= threshold:
            out[name] = Classification(name, winner, (), current.similarity)
    return out
