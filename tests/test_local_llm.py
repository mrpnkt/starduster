"""Taxonomy bootstrap (cluster + name) and local summaries, with a fake LLM."""

import numpy as np
import pytest

from starduster.categorize.bootstrap import bootstrap_taxonomy, slugify
from starduster.categorize.embeddings import EmbeddingSet
from starduster.local.ollama import OllamaError
from starduster.local.summarize import summarize_local
from starduster.models import Repo

QUIET = dict(log=lambda *_: None)


def repo(name, desc="d"):
    return Repo(name, desc, (), 1, None, None, "", "", False, False, "u", "readme")


class FakeLLM:
    def __init__(self, replies=None, fail_on=()):
        self.replies, self.fail_on, self.calls = list(replies or []), fail_on, []

    def chat_json(self, model, prompt, schema, **kw):
        self.calls.append((model, prompt, kw))
        if any(f in prompt for f in self.fail_on):
            raise OllamaError("bad json")
        if "groups" in schema.get("properties", {}):
            ids = [line.split(":")[0].strip("- ") for line in prompt.splitlines() if line.startswith("- ")]
            return {"groups": [{"name": "Everything", "category_ids": ids}]}
        if self.replies:
            return self.replies.pop(0)
        return {"name": f"Cluster Name {len(self.calls)}", "definition": "def"}


def blobs():
    """Three well-separated groups of 10 vectors."""
    rng = np.random.default_rng(1)
    centres = np.eye(3, 16)
    rows = np.vstack([c + 0.05 * rng.normal(size=(10, 16)) for c in centres]).astype(np.float32)
    rows /= np.linalg.norm(rows, axis=1, keepdims=True)
    names = tuple(f"o/r{i}" for i in range(30))
    return EmbeddingSet(names, rows, "d"), {n: repo(n) for n in names}


def test_slugify():
    assert slugify("Post-Exploitation Frameworks!") == "post-exploitation-frameworks"
    assert slugify("  ") == "category"


def test_bootstrap_builds_valid_taxonomy_and_centroids():
    es, repos = blobs()
    tax, cents = bootstrap_taxonomy(es, repos, FakeLLM(), k=3, model="m", version="v1", **QUIET)
    assert len(tax.categories) == 3 and tax.version == "v1"
    assert set(cents.ids) == set(tax.leaf_ids)
    assert cents.vectors.shape == (3, 16)


def test_clusters_recover_the_true_groups():
    es, repos = blobs()
    tax, cents = bootstrap_taxonomy(es, repos, FakeLLM(), k=3, model="m", version="v", **QUIET)
    from starduster.categorize.assign import assign_categories
    got = assign_categories(es, cents, tax, min_similarity=0.0)
    for block in range(3):
        cats = {got[f"o/r{block * 10 + i}"].primary for i in range(10)}
        assert len(cats) == 1


def test_duplicate_names_get_unique_ids():
    es, repos = blobs()
    same = [{"name": "Tools", "definition": "d"}] * 3
    tax, _ = bootstrap_taxonomy(es, repos, FakeLLM(same), k=3, model="m", version="v", **QUIET)
    assert len(set(tax.leaf_ids)) == 3


def test_naming_failure_falls_back_instead_of_aborting():
    es, repos = blobs()
    tax, _ = bootstrap_taxonomy(es, repos, FakeLLM(fail_on=("grouped together",)), k=3,
                                model="m", version="v", **QUIET)
    assert all(c.name.startswith("Cluster ") for c in tax.categories)


def test_grouping_failure_falls_back_to_one_group():
    es, repos = blobs()
    tax, _ = bootstrap_taxonomy(es, repos, FakeLLM(fail_on=("broad groups",)), k=3,
                                model="m", version="v", **QUIET)
    assert len(tax.groups) == 1 and len(tax.categories) == 3


class TestSummarizeLocal:
    def test_builds_summaries_without_labels(self):
        llm = FakeLLM([{"summary": "A CLI.", "labels": ["cli"]}])
        out = summarize_local(llm, [repo("a/1")], model="m", prompt_version="1", **QUIET)
        assert out["a/1"].summary == "A CLI." and out["a/1"].labels == ()
        assert out["a/1"].model == "m" and out["a/1"].version_key == "prompt=1"

    def test_failures_are_skipped_not_fatal(self):
        llm = FakeLLM([{"summary": "ok", "labels": []}], fail_on=("a/bad",))
        out = summarize_local(llm, [repo("a/bad"), repo("b/ok")], model="m", prompt_version="1", **QUIET)
        assert set(out) == {"b/ok"}

    def test_checkpoints_every_n(self):
        llm = FakeLLM([{"summary": f"s{i}", "labels": []} for i in range(5)])
        seen = []
        summarize_local(llm, [repo(f"a/{i}") for i in range(5)], model="m", prompt_version="1",
                        save_every=2, on_progress=lambda d: seen.append(len(d)), **QUIET)
        assert seen == [2, 4, 5]

    def test_summary_length_is_capped(self):
        llm = FakeLLM([{"summary": "x" * 5000, "labels": []}])
        out = summarize_local(llm, [repo("a/1")], model="m", prompt_version="1", **QUIET)
        assert len(out["a/1"].summary) <= 240

    def test_output_tokens_are_capped(self):
        llm = FakeLLM([{"summary": "s", "labels": []}])
        summarize_local(llm, [repo("a/1")], model="m", prompt_version="1", **QUIET)
        assert llm.calls[0][2]["max_tokens"] > 0


def test_distinctive_keywords_prefer_terms_unique_to_a_cluster():
    from starduster.categorize.bootstrap import distinctive_keywords
    shared = "security tool for pentesting"
    clusters = [
        [Repo(f"a/{i}", f"{shared} kerberos ticket forging", ("active-directory",), 1, None, None, "", "", False, False, "u") for i in range(5)],
        [Repo(f"b/{i}", f"{shared} phishing email lure", ("phishing",), 1, None, None, "", "", False, False, "u") for i in range(5)],
    ]
    kw = distinctive_keywords(clusters, top=4)
    assert "kerberos" in kw[0] or "active-directory" in kw[0]
    assert "phishing" in kw[1]
    assert "security" not in kw[0] and "pentesting" not in kw[1], "shared words carry no signal"


def test_naming_prompt_includes_keywords_and_taken_names():
    from starduster.local.prompts import cluster_naming_prompt
    p = cluster_naming_prompt([repo("a/1")], keywords=["kerberos", "tickets"], taken=["OSINT Tools"])
    assert "kerberos" in p and "OSINT Tools" in p


def test_duplicate_names_get_a_distinguishing_keyword():
    es, repos = blobs()
    same = [{"name": "Tools", "definition": "d"}] * 3
    tax, _ = bootstrap_taxonomy(es, repos, FakeLLM(same), k=3, model="m", version="v", **QUIET)
    assert len({c.name for c in tax.categories}) == 3


def test_long_names_are_cut_at_a_word_boundary():
    from starduster.categorize.bootstrap import clip_words
    assert clip_words("System Administration and Penetration Testing Tools", 40) == "System Administration and Penetration"
    assert clip_words("Short", 40) == "Short"
