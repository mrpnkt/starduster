"""Cache-key semantics — these rules decide what the daily run costs."""

from starduster.store.keys import summary_hash
from starduster.models import Repo


def repo(**over):
    base = dict(
        full_name="o/n", description="d", topics=("a", "b"), stars=100,
        language="Python", license="MIT", pushed_at="2026-01-01T00:00:00Z",
        starred_at="2025-01-01T00:00:00Z", is_archived=False, is_fork=False,
        url="u", readme_excerpt="readme text",
    )
    base.update(over)
    return Repo(**base)


class TestStability:
    def test_same_inputs_give_same_key(self):
        assert summary_hash(repo(), "1") == summary_hash(repo(), "1")

    def test_topic_order_does_not_matter(self):
        """Topics are a set semantically; ordering must not thrash the cache."""
        assert summary_hash(repo(topics=("a", "b")), "1") == summary_hash(
            repo(topics=("b", "a")), "1"
        )


class TestVolatileFieldsAreExcluded:
    """Star counts and push dates change daily and must not re-bill the corpus."""

    def test_star_count_change_does_not_invalidate(self):
        assert summary_hash(repo(stars=100), "1") == summary_hash(
            repo(stars=99999), "1"
        )

    def test_push_date_change_does_not_invalidate(self):
        assert summary_hash(repo(pushed_at="2020-01-01T00:00:00Z"), "1") == (
            summary_hash(repo(pushed_at="2026-09-19T00:00:00Z"), "1")
        )

    def test_archived_flag_does_not_invalidate(self):
        assert summary_hash(repo(is_archived=False), "1") == summary_hash(
            repo(is_archived=True), "1"
        )


class TestMeaningfulFieldsInvalidate:
    def test_description_change_invalidates(self):
        assert summary_hash(repo(description="x"), "1") != summary_hash(
            repo(description="y"), "1"
        )

    def test_topic_change_invalidates(self):
        assert summary_hash(repo(topics=("a",)), "1") != summary_hash(
            repo(topics=("a", "c")), "1"
        )

    def test_readme_change_invalidates(self):
        assert summary_hash(repo(readme_excerpt="one"), "1") != summary_hash(
            repo(readme_excerpt="two"), "1"
        )

    def test_language_change_invalidates(self):
        assert summary_hash(repo(language="Go"), "1") != summary_hash(
            repo(language="Rust"), "1"
        )

    def test_prompt_version_bump_invalidates(self):
        assert summary_hash(repo(), "1") != summary_hash(repo(), "2")
