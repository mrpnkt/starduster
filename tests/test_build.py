"""Site payload construction and derived facets."""

import json

import pytest

from starduster.build import (
    build_payload,
    maintenance_bucket,
    star_bucket,
    to_record,
)
from starduster.taxonomy import parse_taxonomy
from starduster.models import CatalogEntry, Classification, Repo, Summary

NOW = "2026-09-19T00:00:00Z"

TAX = parse_taxonomy({
    "version": "t1",
    "groups": [{"id": "g", "name": "G"}],
    "categories": [{"id": "cli-tools", "name": "CLI", "parent": "g",
                    "definition": "d"}],
})


def repo(name="o/n", **over):
    base = dict(
        full_name=name, description="desc", topics=("t",), stars=500,
        language="Python", license="MIT", pushed_at="2026-09-01T00:00:00Z",
        starred_at="2025-01-01T00:00:00Z", is_archived=False, is_fork=False,
        url="https://github.com/o/n", readme_excerpt="long readme",
    )
    base.update(over)
    return Repo(**base)


class TestMaintenanceBucket:
    def test_archived_wins_over_recency(self):
        """An archived repo is dead even if it was pushed yesterday."""
        assert maintenance_bucket(
            repo(is_archived=True, pushed_at="2026-09-18T00:00:00Z"), NOW
        ) == "archived"

    def test_recent_push_is_active(self):
        assert maintenance_bucket(repo(pushed_at="2026-09-01T00:00:00Z"), NOW) == "active"

    def test_one_year_is_stale(self):
        assert maintenance_bucket(repo(pushed_at="2025-09-19T00:00:00Z"), NOW) == "stale"

    def test_three_years_is_dormant(self):
        assert maintenance_bucket(repo(pushed_at="2023-01-01T00:00:00Z"), NOW) == "dormant"

    def test_boundaries(self):
        # 183-day active/stale boundary, 730-day stale/dormant boundary.
        assert maintenance_bucket(repo(pushed_at="2026-03-21T00:00:00Z"), NOW) == "active"
        assert maintenance_bucket(repo(pushed_at="2026-03-18T00:00:00Z"), NOW) == "stale"
        assert maintenance_bucket(repo(pushed_at="2024-09-21T00:00:00Z"), NOW) == "stale"
        assert maintenance_bucket(repo(pushed_at="2024-09-18T00:00:00Z"), NOW) == "dormant"

    def test_missing_push_date_is_unknown(self):
        assert maintenance_bucket(repo(pushed_at=""), NOW) == "unknown"

    def test_malformed_push_date_is_unknown(self):
        assert maintenance_bucket(repo(pushed_at="not-a-date"), NOW) == "unknown"


class TestStarBucket:
    @pytest.mark.parametrize("stars,expected", [
        (0, "<100"), (99, "<100"), (100, "100-1k"), (999, "100-1k"),
        (1_000, "1k-10k"), (9_999, "1k-10k"), (10_000, "10k-50k"),
        (49_999, "10k-50k"), (50_000, "50k+"), (250_000, "50k+"),
    ])
    def test_buckets(self, stars, expected):
        assert star_bucket(stars) == expected


class TestToRecord:
    def entry(self, **over):
        r = repo(**over.pop("repo", {}))
        return CatalogEntry(
            repo=r,
            summary=over.get("summary", Summary(r.full_name, "what it is",
                                                ("cli",), "h", "m")),
            classification=over.get("classification",
                                    Classification(r.full_name, "cli-tools", (), 0.9)),
        )

    def test_includes_generated_summary_and_category(self):
        rec = to_record(self.entry(), NOW)
        assert rec["summary"] == "what it is"
        assert rec["category"] == "cli-tools"
        assert rec["labels"] == ["cli"]

    def test_excludes_readme_from_payload(self):
        """READMEs are prompt input only; shipping them would bloat the page."""
        rec = to_record(self.entry(), NOW)
        assert "readme" not in json.dumps(rec).lower() or "long readme" not in json.dumps(rec)

    def test_derived_facets_present(self):
        rec = to_record(self.entry(), NOW)
        assert rec["maintenance"] == "active"
        assert rec["stars_bucket"] == "100-1k"
        assert rec["starred_year"] == "2025"

    def test_unclassified_repo_still_renders(self):
        rec = to_record(
            CatalogEntry(repo=repo(), summary=None, classification=None), NOW)
        assert rec["category"] is None
        assert rec["summary"] == ""
        assert rec["name"] == "o/n"

    def test_falls_back_to_description_when_no_summary(self):
        rec = to_record(
            CatalogEntry(repo=repo(), summary=None, classification=None), NOW)
        assert rec["description"] == "desc"


class TestBuildPayload:
    def test_includes_taxonomy_and_counts(self):
        entries = (CatalogEntry(repo(), None, None),)
        payload = build_payload(entries, TAX, now=NOW)
        assert payload["meta"]["total"] == 1
        assert payload["taxonomy"]["version"] == "t1"
        assert len(payload["repos"]) == 1

    def test_reports_unclassified_count(self):
        entries = (
            CatalogEntry(repo("a/1"), None, None),
            CatalogEntry(repo("b/2"), None,
                         Classification("b/2", "cli-tools", (), 0.9)),
        )
        payload = build_payload(entries, TAX, now=NOW)
        assert payload["meta"]["unclassified"] == 1

    def test_counts_untagged_repos(self):
        """The headline statistic the project exists to fix."""
        entries = (
            CatalogEntry(repo("a/1", topics=()), None, None),
            CatalogEntry(repo("b/2", topics=("x",)), None, None),
        )
        payload = build_payload(entries, TAX, now=NOW)
        assert payload["meta"]["untagged"] == 1

    def test_is_json_serializable(self):
        entries = (CatalogEntry(repo(), None, None),)
        json.dumps(build_payload(entries, TAX, now=NOW))


def test_similar_names_become_indices_into_repos():
    a, b, c = (CatalogEntry(repo(n, starred_at=f"2025-0{i}-01T00:00:00Z"), None, None)
               for i, n in enumerate(["a/1", "b/2", "c/3"], 1))
    payload = build_payload((a, b, c), TAX, similar={"a/1": ["c/3", "gone/9", "b/2"]}, now=NOW)
    assert payload["repos"][0]["similar"] == [2, 1], "unknown names dropped, order kept"
    assert payload["repos"][1]["similar"] == []
