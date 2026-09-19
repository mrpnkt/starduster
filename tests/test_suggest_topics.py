"""Suggested topics for untagged repos, borrowed from similar tagged repos."""

import numpy as np

from starduster.categorize.embeddings import EmbeddingSet
from starduster.categorize.topics import suggest_topics, topic_vocabulary
from starduster.models import Repo


def unit(*v):
    a = np.asarray(v, dtype=np.float32)
    return a / np.linalg.norm(a)


def repo(name, topics=()):
    return Repo(name, "", tuple(topics), 1, None, None, "", "", False, False, "u")


def corpus():
    """Four tagged OSINT repos near (1,0), four tagged web repos near (0,1), one untagged near OSINT."""
    rows, repos = [], []
    for i in range(4):
        repos.append(repo(f"o/{i}", ["osint", "recon"] + (["hacktoberfest"] if i < 3 else [])))
        rows.append(unit(1, 0.05 * i, 0))
    for i in range(4):
        repos.append(repo(f"w/{i}", ["web", "xss"]))
        rows.append(unit(0.05 * i, 1, 0))
    repos.append(repo("u/new"))
    rows.append(unit(1, 0.1, 0.05))
    return repos, EmbeddingSet(tuple(r.full_name for r in repos), np.stack(rows), "d")


def test_vocabulary_keeps_reused_topics_and_drops_stop_topics():
    repos, _ = corpus()
    vocab = topic_vocabulary(repos, min_uses=3, stop=("hacktoberfest",))
    assert vocab == {"osint", "recon", "web", "xss"}


def test_untagged_repo_gets_topics_its_neighbours_share():
    repos, es = corpus()
    out = suggest_topics(repos, es, k=4, min_votes=3, max_topics=5, min_uses=3)
    assert set(out["u/new"]) == {"osint", "recon"}


def test_tagged_repos_get_no_suggestions():
    repos, es = corpus()
    out = suggest_topics(repos, es, k=4, min_votes=3, max_topics=5, min_uses=3)
    assert set(out) == {"u/new"}


def test_min_votes_filters_weak_agreement():
    repos, es = corpus()
    out = suggest_topics(repos, es, k=8, min_votes=5, max_topics=5, min_uses=3)
    assert out["u/new"] == []


def test_max_topics_caps_output_ordered_by_support():
    repos, es = corpus()
    out = suggest_topics(repos, es, k=4, min_votes=1, max_topics=1, min_uses=3)
    assert len(out["u/new"]) == 1


def test_repo_without_embedding_is_skipped():
    repos, es = corpus()
    out = suggest_topics(repos + [repo("x/unembedded")], es, k=4, min_votes=3, max_topics=5, min_uses=3)
    assert "x/unembedded" not in out


def test_deterministic():
    repos, es = corpus()
    kw = dict(k=4, min_votes=3, max_topics=5, min_uses=3)
    assert suggest_topics(repos, es, **kw) == suggest_topics(repos, es, **kw)


def test_no_tagged_repos_means_no_suggestions():
    es = EmbeddingSet(("u/1",), np.stack([unit(1, 0)]), "d")
    assert suggest_topics([repo("u/1")], es) == {"u/1": []}
