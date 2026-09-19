"""`starduster taxonomy`: cluster the embeddings, then let a local LLM name them.

Runs on your machine only. Needs scikit-learn (`pip install -e ".[local]"`).
The result is a starting point to edit by hand, so the LLM steps degrade to
placeholder names rather than aborting a run.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Mapping, Sequence

import numpy as np

from ..config import TAXONOMY_EXAMPLES_PER_CLUSTER
from ..local.ollama import OllamaError
from ..local.prompts import cluster_naming_prompt, grouping_prompt
from ..local.schema import CLUSTER_NAME_SCHEMA, GROUPING_SCHEMA
from ..models import Category, Group, Repo, Taxonomy
from .centroids import Centroids
from .embeddings import EmbeddingSet


_WORD = re.compile(r"[a-z][a-z0-9+#-]{2,}")
_STOP = frozenset("""
the and for with from that this your you are can use using used into via tool tools
based simple small fast easy written project projects repository repo collection list
support supports allows all any has have not new more most get set run runs its also
""".split())
KEYWORDS_PER_CLUSTER = 8


def _terms(repo: Repo) -> list[str]:
    words = [w for w in _WORD.findall(repo.description.lower()) if w not in _STOP]
    return words + [t.lower() for t in repo.topics] * 2  # topics are deliberate labels


def distinctive_keywords(clusters: Sequence[Sequence[Repo]], top: int = KEYWORDS_PER_CLUSTER) -> list[list[str]]:
    """c-TF-IDF: terms frequent in one cluster but rare across all of them."""
    counts = [Counter(t for r in repos for t in _terms(r)) for repos in clusters]
    spread = Counter(t for c in counts for t in c)  # clusters containing each term
    k = len(counts)
    out = []
    for c in counts:
        total = sum(c.values()) or 1
        score = {t: (n / total) * math.log(1 + k / spread[t]) for t, n in c.items() if n > 1}
        out.append([t for t, _ in sorted(score.items(), key=lambda kv: -kv[1])[:top]])
    return out


def clip_words(text: str, limit: int) -> str:
    """Shorten to at most `limit` chars without cutting a word in half."""
    if len(text) <= limit:
        return text
    return text[:limit + 1].rsplit(" ", 1)[0].rstrip(" ,;:-")


def _dedupe(name: str, taken: list[str], keywords: Sequence[str], index: int) -> str:
    """Small models sometimes ignore the list of taken names; break the tie."""
    if name not in taken:
        return name
    for word in keywords:
        candidate = f"{name}: {word.replace('-', ' ').title()}"
        if candidate not in taken:
            return candidate
    return f"{name} {index + 1}"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "category"


def _kmeans(vectors: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    try:
        from sklearn.cluster import KMeans
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise SystemExit(
            "Clustering needs scikit-learn: run `pip install -e \".[local]\"`."
        ) from exc
    km = KMeans(n_clusters=k, n_init=5, random_state=0).fit(vectors)
    centres = km.cluster_centers_
    centres = centres / np.linalg.norm(centres, axis=1, keepdims=True)
    return km.labels_, centres.astype(np.float32)


def _examples(es: EmbeddingSet, labels: np.ndarray, centres: np.ndarray, n: int) -> list[list[str]]:
    sims = es.vectors @ centres.T
    out = []
    for c in range(len(centres)):
        members = np.where(labels == c)[0]
        nearest = members[np.argsort(-sims[members, c])][:n]
        out.append([es.names[i] for i in nearest])
    return out


def _name(llm: Any, model: str, index: int, examples: list[Repo], log,
          keywords: list[str] = (), taken: list[str] = ()) -> tuple[str, str]:
    try:
        prompt = cluster_naming_prompt(examples, keywords=list(keywords), taken=list(taken))
        reply = llm.chat_json(model, prompt, CLUSTER_NAME_SCHEMA)
        name = clip_words(str(reply.get("name") or "").strip(), 60)
        definition = str(reply.get("definition") or "").strip()[:300]
        if name:
            return name, definition
    except OllamaError as exc:
        log(f"  cluster {index}: naming failed ({exc}); using a placeholder")
    sample = ", ".join(r.full_name.split("/")[-1] for r in examples[:5])
    return f"Cluster {index + 1}", f"Unnamed cluster, e.g. {sample}."


def _unique_ids(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    ids = []
    for name in names:
        base = slugify(name)
        seen[base] = seen.get(base, 0) + 1
        ids.append(base if seen[base] == 1 else f"{base}-{seen[base]}")
    return ids


def _group(llm: Any, model: str, cats: list[tuple[str, str]], log) -> tuple[tuple[Group, ...], dict[str, str]]:
    """Ask the LLM for sidebar groups; every category lands in exactly one."""
    fallback = ((Group("all", "All categories"),), {cid: "all" for cid, _ in cats})
    try:
        reply = llm.chat_json(model, grouping_prompt(cats), GROUPING_SCHEMA)
    except OllamaError as exc:
        log(f"  grouping failed ({exc}); using a single group")
        return fallback
    known = {cid for cid, _ in cats}
    groups, parent_of = [], {}
    for raw in reply.get("groups") or []:
        members = [c for c in raw.get("category_ids") or [] if c in known and c not in parent_of]
        if not members:
            continue
        gid = f"group-{len(groups) + 1}"
        groups.append(Group(gid, clip_words(str(raw.get("name") or gid), 40)))
        parent_of.update({c: gid for c in members})
    leftovers = [cid for cid, _ in cats if cid not in parent_of]
    if not groups:
        return fallback
    if leftovers:
        groups.append(Group("other", "Other"))
        parent_of.update({c: "other" for c in leftovers})
    return tuple(groups), parent_of


def bootstrap_taxonomy(
    es: EmbeddingSet,
    repos: Mapping[str, Repo],
    llm: Any,
    *,
    k: int,
    model: str,
    version: str,
    examples_per_cluster: int = TAXONOMY_EXAMPLES_PER_CLUSTER,
    log=print,
) -> tuple[Taxonomy, Centroids]:
    log(f"  clustering {len(es.names)} repos into {k} groups")
    labels, centres = _kmeans(es.vectors, k)
    examples = _examples(es, labels, centres, examples_per_cluster)
    members = [[repos[es.names[j]] for j in range(len(es.names))
                if labels[j] == c and es.names[j] in repos] for c in range(k)]
    keywords = distinctive_keywords(members)

    named: list[tuple[str, str]] = []
    for i, names in enumerate(examples):
        taken = [n for n, _ in named]
        name, definition = _name(llm, model, i, [repos[n] for n in names if n in repos], log,
                                 keywords[i], taken)
        named.append((_dedupe(name, taken, keywords[i], i), definition))
        log(f"  [{i + 1}/{k}] {named[-1][0]} ({int((labels == i).sum())} repos)")

    ids = _unique_ids([n for n, _ in named])
    groups, parent_of = _group(llm, model, list(zip(ids, (n for n, _ in named))), log)
    categories = tuple(
        Category(id=cid, name=name, definition=definition, parent=parent_of[cid])
        for cid, (name, definition) in zip(ids, named)
    )
    return (
        Taxonomy(version=version, groups=groups, categories=categories),
        Centroids(version, tuple(ids), centres),
    )
