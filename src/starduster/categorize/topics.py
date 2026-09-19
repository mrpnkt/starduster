"""Suggested topics for repos that have none.

Half of this collection has no GitHub topics. Each untagged repo borrows the
topics that at least `min_votes` of its `k` most similar *tagged* repos share,
restricted to topics the collection already uses repeatedly, so suggestions
never invent new vocabulary. Free, deterministic, recomputed every build.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Sequence

import numpy as np

from ..config import (
    SUGGEST_MAX_TOPICS,
    SUGGEST_MIN_TOPIC_USES,
    SUGGEST_MIN_VOTES,
    SUGGEST_NEIGHBOURS,
    SUGGEST_STOP_TOPICS,
)
from ..models import Repo
from .embeddings import EmbeddingSet


def topic_vocabulary(
    repos: Iterable[Repo],
    min_uses: int = SUGGEST_MIN_TOPIC_USES,
    stop: Sequence[str] = SUGGEST_STOP_TOPICS,
) -> set[str]:
    counts = Counter(t for r in repos for t in r.topics)
    return {t for t, n in counts.items() if n >= min_uses and t not in stop}


def suggest_topics(
    repos: Sequence[Repo],
    es: EmbeddingSet,
    *,
    k: int = SUGGEST_NEIGHBOURS,
    min_votes: int = SUGGEST_MIN_VOTES,
    max_topics: int = SUGGEST_MAX_TOPICS,
    min_uses: int = SUGGEST_MIN_TOPIC_USES,
    stop: Sequence[str] = SUGGEST_STOP_TOPICS,
) -> dict[str, list[str]]:
    """Map each embedded, untagged repo to its suggested topics (possibly [])."""
    vocab = topic_vocabulary(repos, min_uses, stop)
    by_name = {r.full_name: r for r in repos}
    index = {n: i for i, n in enumerate(es.names)}

    tagged = [n for n in es.names if n in by_name and set(by_name[n].topics) & vocab]
    untagged = [r.full_name for r in repos if not r.topics and r.full_name in index]
    if not untagged:
        return {}
    if not tagged:
        return {n: [] for n in untagged}

    tagged_vectors = es.vectors[[index[n] for n in tagged]]
    queries = es.vectors[[index[n] for n in untagged]]
    sims = queries @ tagged_vectors.T
    k = min(k, len(tagged))

    out: dict[str, list[str]] = {}
    for row, name in enumerate(untagged):
        nearest = np.argsort(-sims[row], kind="stable")[:k]
        votes: Counter[str] = Counter()
        support: Counter[str] = Counter()
        for j in nearest:
            for topic in set(by_name[tagged[j]].topics) & vocab:
                votes[topic] += 1
                support[topic] += float(sims[row, j])
        chosen = [t for t in votes if votes[t] >= min_votes]
        out[name] = sorted(chosen, key=lambda t: (-support[t], t))[:max_topics]
    return out
