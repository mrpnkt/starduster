"""Embedding storage, nearest-centre categories, similar repos, parity probe."""

import numpy as np
import pytest

from starduster.categorize.assign import assign_categories
from starduster.categorize.embeddings import (
    EmbeddingSet,
    EmbeddingError,
    load_embeddings,
    save_embeddings,
)
from starduster.categorize.centroids import Centroids, load_centroids, save_centroids
from starduster.categorize.probe import PROBE_TEXTS, ProbeError, check_probe
from starduster.categorize.similar import similar_indices
from starduster.categorize.text import embedding_text
from starduster.models import Repo
from starduster.taxonomy import parse_taxonomy


def unit(*v):
    a = np.asarray(v, dtype=np.float32)
    return a / np.linalg.norm(a)


def repo(name="o/n", **over):
    base = dict(full_name=name, description="A tool", topics=("cli", "go"), stars=1,
                language="Go", license=None, pushed_at="", starred_at="",
                is_archived=False, is_fork=False, url="u", readme_excerpt="# Readme\nbody")
    base.update(over)
    return Repo(**base)


class TestEmbeddingText:
    def test_has_prefix_name_description_topics_readme(self):
        t = embedding_text(repo())
        assert t.startswith("clustering: o/n")
        assert "A tool" in t and "cli, go" in t and "body" in t

    def test_readme_is_capped(self):
        from starduster.tokens import estimate_tokens
        t = embedding_text(repo(readme_excerpt="word " * 50_000))
        assert estimate_tokens(t) < 800

    def test_repo_with_nothing_still_embeds_its_name(self):
        t = embedding_text(repo(description="", topics=(), readme_excerpt=""))
        assert t == "clustering: o/n"


class TestEmbeddingSet:
    def es(self):
        return EmbeddingSet(("a/1", "b/2"), np.stack([unit(1, 0), unit(0, 1)]), "digest1")

    def test_missing_lists_unembedded_repos(self):
        assert self.es().missing([repo("a/1"), repo("c/3")]) == (repo("c/3"),)

    def test_with_added_returns_new_set(self):
        base = self.es()
        new = base.with_added(("c/3",), np.stack([unit(1, 1)]))
        assert base.names == ("a/1", "b/2") and new.names == ("a/1", "b/2", "c/3")

    def test_adding_under_a_different_model_is_refused(self):
        with pytest.raises(EmbeddingError, match="digest"):
            self.es().with_added(("c/3",), np.stack([unit(1, 1)]), digest="other")

    def test_round_trip(self, tmp_path):
        p = tmp_path / "e.npz"
        save_embeddings(p, self.es())
        back = load_embeddings(p)
        assert back.names == ("a/1", "b/2") and back.digest == "digest1"
        assert np.allclose(back.vectors, self.es().vectors, atol=1e-3)

    def test_missing_file_is_empty_set(self, tmp_path):
        assert load_embeddings(tmp_path / "none.npz").names == ()

    def test_vector_lookup(self):
        assert np.allclose(self.es().vector("b/2"), unit(0, 1))
        assert self.es().vector("zzz") is None


TAX = parse_taxonomy({"version": "t1", "groups": [{"id": "g", "name": "G"}], "categories": [
    {"id": "x", "name": "X", "parent": "g", "definition": ""},
    {"id": "y", "name": "Y", "parent": "g", "definition": ""}]})


class TestAssign:
    cents = Centroids("t1", ("x", "y", "gone"), np.stack([unit(1, 0, 0), unit(0, 1, 0), unit(0, 0, 1)]))

    def test_nearest_centre_wins(self):
        es = EmbeddingSet(("a/1",), np.stack([unit(0.9, 0.1, 0)]), "d")
        out = assign_categories(es, self.cents, TAX, min_similarity=0.5)
        assert out["a/1"].primary == "x"

    def test_below_threshold_is_unsorted(self):
        es = EmbeddingSet(("a/1",), np.stack([unit(1, 1, 1)]), "d")
        out = assign_categories(es, self.cents, TAX, min_similarity=0.9)
        assert out["a/1"].primary is None

    def test_close_runner_up_becomes_secondary(self):
        es = EmbeddingSet(("a/1",), np.stack([unit(1, 0.98, 0)]), "d")
        out = assign_categories(es, self.cents, TAX, min_similarity=0.1, secondary_margin=0.05)
        assert out["a/1"].primary == "x" and out["a/1"].secondary == ("y",)

    def test_category_deleted_from_taxonomy_merges_into_nearest(self):
        """'gone' has a centroid but is not in the taxonomy any more."""
        es = EmbeddingSet(("a/1",), np.stack([unit(0.1, 0.3, 1)]), "d")
        out = assign_categories(es, self.cents, TAX, min_similarity=0.0)
        assert out["a/1"].primary == "y"

    def test_seeds_define_a_hand_added_category(self):
        """A category with `seeds` gets the mean of those repos as its centre."""
        tax = parse_taxonomy({"version": "t2", "groups": [{"id": "g", "name": "G"}], "categories": [
            {"id": "x", "name": "X", "parent": "g", "definition": ""},
            {"id": "new", "name": "New", "parent": "g", "definition": "", "seeds": ["s/1", "s/2"]}]})
        es = EmbeddingSet(("s/1", "s/2", "a/1"),
                          np.stack([unit(0, 0, 1), unit(0, 0.2, 1), unit(0, 0.1, 1)]), "d")
        out = assign_categories(es, self.cents, tax, min_similarity=0.5)
        assert out["a/1"].primary == "new"

    def test_category_with_no_centre_and_no_seeds_is_reported(self):
        from starduster.categorize.assign import categories_without_centre
        tax = parse_taxonomy({"version": "t", "groups": [{"id": "g", "name": "G"}], "categories": [
            {"id": "x", "name": "X", "parent": "g", "definition": ""},
            {"id": "orphan", "name": "O", "parent": "g", "definition": ""}]})
        es = EmbeddingSet((), np.zeros((0, 3), np.float32), "d")
        assert categories_without_centre(tax, self.cents, es) == ("orphan",)

    def test_deterministic(self):
        es = EmbeddingSet(("a/1",), np.stack([unit(0.9, 0.1, 0)]), "d")
        assert assign_categories(es, self.cents, TAX) == assign_categories(es, self.cents, TAX)


def test_centroids_round_trip(tmp_path):
    c = Centroids("t1", ("x", "y"), np.stack([unit(1, 0), unit(0, 1)]))
    save_centroids(tmp_path / "c.npz", c)
    back = load_centroids(tmp_path / "c.npz")
    assert back.taxonomy_version == "t1" and back.ids == ("x", "y")


class TestSimilar:
    def test_excludes_self_and_orders_by_similarity(self):
        m = np.stack([unit(1, 0), unit(0.9, 0.1), unit(0, 1), unit(0.5, 0.5)])
        out = similar_indices(m, k=2)
        assert out[0] == [1, 3]
        assert all(i not in row for i, row in enumerate(out))

    def test_k_larger_than_corpus(self):
        assert similar_indices(np.stack([unit(1, 0), unit(0, 1)]), k=10) == [[1], [0]]

    def test_chunking_gives_same_answer(self):
        rng = np.random.default_rng(0)
        m = rng.normal(size=(50, 8)).astype(np.float32)
        m /= np.linalg.norm(m, axis=1, keepdims=True)
        assert similar_indices(m, k=5, chunk=7) == similar_indices(m, k=5, chunk=1000)


class TestProbe:
    def test_matching_vectors_pass(self):
        ref = np.stack([unit(1, 0), unit(0, 1)])
        check_probe(ref, ref.copy(), min_similarity=0.99)

    def test_drifted_vectors_fail_with_explanation(self):
        ref = np.stack([unit(1, 0), unit(0, 1)])
        with pytest.raises(ProbeError, match="re-embed"):
            check_probe(ref, np.stack([unit(1, 0), unit(1, 1)]), min_similarity=0.99)

    def test_probe_texts_are_fixed(self):
        assert len(PROBE_TEXTS) >= 3


def test_appending_repos_keeps_the_stored_bytes_as_a_prefix(tmp_path):
    """Git deltas appended data cheaply; a rewritten/compressed file it cannot."""
    base = EmbeddingSet(("a/1", "b/2"), np.stack([unit(1, 0), unit(0, 1)]), "d")
    save_embeddings(tmp_path / "one.npz", base)
    save_embeddings(tmp_path / "two.npz", base.with_added(("c/3",), np.stack([unit(1, 1)])))
    one, two = (tmp_path / "one.npz").read_bytes(), (tmp_path / "two.npz").read_bytes()
    import difflib
    ratio = difflib.SequenceMatcher(None, one, two, autojunk=False).ratio()
    assert ratio > 0.8


class TestNeighbourConsensus:
    """Override the nearest centre only when a repo's neighbours clearly agree."""
    cents = Centroids("t", ("x", "y"), np.stack([unit(1, 0, 0), unit(0, 1, 0)]))
    tax = parse_taxonomy({"version": "t", "groups": [{"id": "g", "name": "G"}], "categories": [
        {"id": "x", "name": "X", "parent": "g", "definition": ""},
        {"id": "y", "name": "Y", "parent": "g", "definition": ""}]})

    def es(self):
        # a/0 sits slightly closer to centre x, but all its neighbours are y.
        rows = [unit(0.60, 0.55, 0.3)] + [unit(0.1, 1, 0.2 + i / 10) for i in range(4)]
        return EmbeddingSet(tuple(f"a/{i}" for i in range(5)), np.stack(rows), "d")

    def test_strong_consensus_overrides_centre(self):
        neighbours = [[1, 2, 3, 4], [0, 2, 3, 4], [0, 1, 3, 4], [0, 1, 2, 4], [0, 1, 2, 3]]
        out = assign_categories(self.es(), self.cents, self.tax, min_similarity=0.0,
                                neighbours=neighbours, consensus=0.6)
        assert out["a/0"].primary == "y"

    def test_without_neighbours_centre_wins(self):
        out = assign_categories(self.es(), self.cents, self.tax, min_similarity=0.0)
        assert out["a/0"].primary == "x"

    def test_split_neighbourhood_does_not_override(self):
        es = EmbeddingSet(("a/0", "b/x", "c/y"),
                          np.stack([unit(0.6, 0.55, 0), unit(1, 0, 0), unit(0, 1, 0)]), "d")
        out = assign_categories(es, self.cents, self.tax, min_similarity=0.0,
                                neighbours=[[1, 2], [0, 2], [0, 1]], consensus=0.6)
        assert out["a/0"].primary == "x"


class TestPins:
    def test_pin_overrides_everything(self):
        tax = parse_taxonomy({"version": "t", "groups": [{"id": "g", "name": "G"}],
                              "categories": [{"id": "x", "name": "X", "parent": "g", "definition": ""},
                                             {"id": "y", "name": "Y", "parent": "g", "definition": ""}],
                              "pins": {"a/1": "y"}})
        cents = Centroids("t", ("x", "y"), np.stack([unit(1, 0), unit(0, 1)]))
        es = EmbeddingSet(("a/1",), np.stack([unit(1, 0)]), "d")
        assert assign_categories(es, cents, tax)["a/1"].primary == "y"

    def test_pin_to_unknown_category_is_rejected(self):
        from starduster.taxonomy import TaxonomyError
        with pytest.raises(TaxonomyError, match="pin"):
            parse_taxonomy({"version": "t", "groups": [{"id": "g", "name": "G"}],
                            "categories": [{"id": "x", "name": "X", "parent": "g", "definition": ""}],
                            "pins": {"a/1": "nope"}})

    def test_pins_round_trip(self):
        from starduster.taxonomy import taxonomy_to_dict
        tax = parse_taxonomy({"version": "t", "groups": [{"id": "g", "name": "G"}],
                              "categories": [{"id": "x", "name": "X", "parent": "g", "definition": ""}],
                              "pins": {"a/1": "x"}})
        assert parse_taxonomy(taxonomy_to_dict(tax)).pins == {"a/1": "x"}


def test_recentre_moves_centres_to_member_means_and_keeps_ids():
    from starduster.categorize.centroids import recentre
    old = Centroids("t", ("x", "y"), np.stack([unit(1, 0), unit(0, 1)]))
    es = EmbeddingSet(("a/1", "a/2", "b/1"), np.stack([unit(1, 0.2), unit(1, 0.4), unit(0.1, 1)]), "d")
    new = recentre(old, {"a/1": "x", "a/2": "x", "b/1": "y"}, es)
    assert new.ids == ("x", "y")
    assert np.allclose(new.vector("x"), unit(2, 0.6), atol=1e-2)


def test_recentre_keeps_old_centre_for_a_category_without_members():
    from starduster.categorize.centroids import recentre
    old = Centroids("t", ("x", "y"), np.stack([unit(1, 0), unit(0, 1)]))
    es = EmbeddingSet(("a/1",), np.stack([unit(1, 0.2)]), "d")
    new = recentre(old, {"a/1": "x"}, es)
    assert np.allclose(new.vector("y"), unit(0, 1))
