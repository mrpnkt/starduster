"""Raw GraphQL node -> Repo. Pure, no network."""

import pytest

from starduster.github.normalize import (
    normalize_edge,
    normalize_edges,
    pick_readme,
)


def make_edge(**over):
    node = {
        "nameWithOwner": "owner/name",
        "description": "A thing",
        "stargazerCount": 42,
        "pushedAt": "2026-01-02T03:04:05Z",
        "isArchived": False,
        "isFork": False,
        "url": "https://github.com/owner/name",
        "primaryLanguage": {"name": "Python"},
        "licenseInfo": {"spdxId": "MIT"},
        "repositoryTopics": {"nodes": [{"topic": {"name": "cli"}}]},
    }
    node.update(over.pop("node", {}))
    edge = {"starredAt": "2025-06-01T00:00:00Z", "node": node}
    edge.update(over)
    return edge


def test_maps_core_fields():
    repo = normalize_edge(make_edge())
    assert repo.full_name == "owner/name"
    assert repo.stars == 42
    assert repo.language == "Python"
    assert repo.license == "MIT"
    assert repo.topics == ("cli",)
    assert repo.starred_at == "2025-06-01T00:00:00Z"


def test_null_language_and_license_become_none():
    # 424 repos in the real corpus have no detected language.
    repo = normalize_edge(
        make_edge(node={"primaryLanguage": None, "licenseInfo": None})
    )
    assert repo.language is None
    assert repo.license is None


def test_null_description_becomes_empty_string():
    # 181 repos in the real corpus have no description.
    repo = normalize_edge(make_edge(node={"description": None}))
    assert repo.description == ""


def test_preserves_commas_quotes_newlines_and_cjk():
    """The exact class of content that made the old CSV format unusable."""
    nasty = 'Turn images into pixel-art，for "indie" devs, fast\nsecond line'
    repo = normalize_edge(make_edge(node={"description": nasty}))
    assert repo.description == nasty


def test_missing_topics_yields_empty_tuple():
    # 1,674 of 3,267 repos (51.2%) have zero topics.
    repo = normalize_edge(make_edge(node={"repositoryTopics": {"nodes": []}}))
    assert repo.topics == ()


def test_topics_are_deduplicated_and_ordered():
    topics = {"nodes": [{"topic": {"name": "b"}}, {"topic": {"name": "a"}},
                        {"topic": {"name": "b"}}]}
    repo = normalize_edge(make_edge(node={"repositoryTopics": topics}))
    assert repo.topics == ("a", "b")


def test_null_node_is_skipped_not_fatal():
    """GitHub returns null nodes for repos that became inaccessible."""
    edges = [
        make_edge(node={"nameWithOwner": "a/one"}),
        {"starredAt": "x", "node": None},
        make_edge(node={"nameWithOwner": "b/two"}),
    ]
    repos = normalize_edges(edges)
    assert [r.full_name for r in repos] == ["a/one", "b/two"]


def test_normalize_edges_is_deterministic_and_deduplicates():
    dup = [make_edge(), make_edge()]
    repos = normalize_edges(dup)
    assert len(repos) == 1


def test_archived_and_fork_flags():
    repo = normalize_edge(make_edge(node={"isArchived": True, "isFork": True}))
    assert repo.is_archived and repo.is_fork


class TestPickReadme:
    def test_prefers_first_populated_alias_in_order(self):
        node = {"readme_0": None, "readme_1": {"text": "second"},
                "readme_2": {"text": "third"}}
        assert pick_readme(node) == "second"

    def test_returns_empty_when_no_readme_present(self):
        assert pick_readme({"readme_0": None, "readme_1": None}) == ""

    def test_ignores_blobs_without_text(self):
        # A Blob on a binary/LFS file has no usable `text`.
        assert pick_readme({"readme_0": {"text": None}}) == ""

    def test_ignores_whitespace_only_readme(self):
        assert pick_readme({"readme_0": {"text": "   \n "}, "readme_1": {"text": "ok"}}) == "ok"
