"""Atomic JSON I/O and the pure merge that joins fetch output with caches."""

import json

import pytest

from starduster.models import Classification, Repo, Summary
from starduster.store.io import read_json, write_json
from starduster.store.merge import build_catalog, repos_needing_summary


def repo(name="o/n", **over):
    base = dict(
        full_name=name, description="d", topics=("t",), stars=1,
        language="Python", license="MIT", pushed_at="2026-01-01T00:00:00Z",
        starred_at="2025-01-01T00:00:00Z", is_archived=False, is_fork=False,
        url="u", readme_excerpt="r",
    )
    base.update(over)
    return Repo(**base)


class TestAtomicIO:
    def test_round_trips(self, tmp_path):
        p = tmp_path / "x.json"
        write_json(p, {"a": [1, 2]})
        assert read_json(p) == {"a": [1, 2]}

    def test_creates_parent_directories(self, tmp_path):
        p = tmp_path / "deep" / "nested" / "x.json"
        write_json(p, {"ok": True})
        assert read_json(p) == {"ok": True}

    def test_missing_file_returns_default(self, tmp_path):
        assert read_json(tmp_path / "nope.json", default={}) == {}

    def test_corrupt_file_returns_default(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not json")
        assert read_json(p, default={"fallback": 1}) == {"fallback": 1}

    def test_leaves_no_temp_files_behind(self, tmp_path):
        write_json(tmp_path / "x.json", {"a": 1})
        assert [f.name for f in tmp_path.iterdir()] == ["x.json"]

    def test_preserves_non_ascii_without_escaping(self, tmp_path):
        """Descriptions contain CJK; the old CSV mangled them."""
        p = tmp_path / "x.json"
        write_json(p, {"d": "pixel-art，for devs"})
        assert "，" in p.read_text(encoding="utf-8")
        assert read_json(p)["d"] == "pixel-art，for devs"

    def test_write_is_deterministic_for_stable_cache_diffs(self, tmp_path):
        a, b = tmp_path / "a.json", tmp_path / "b.json"
        write_json(a, {"z": 1, "a": 2})
        write_json(b, {"a": 2, "z": 1})
        assert a.read_text() == b.read_text()


class TestNeedsWork:
    """Selection rules. Pay-once semantics are covered in test_pay_once.py."""

    def test_repo_with_no_summary_needs_one(self):
        assert repos_needing_summary([repo()], {}, "v1") == (repo(),)

    def test_summarized_repo_is_skipped(self):
        from starduster.store.keys import summary_hash, summary_version_key
        r = repo()
        cached = {r.full_name: Summary(r.full_name, "s", (), summary_hash(r, "v1"), "m",
                                       summary_version_key("v1"))}
        assert repos_needing_summary([r], cached, "v1") == ()

    def test_legacy_entry_without_version_key_is_redone_once(self):
        from starduster.store.keys import summary_hash
        r = repo()
        cached = {r.full_name: Summary(r.full_name, "s", (), summary_hash(r, "v1"), "m")}
        assert repos_needing_summary([r], cached, "v1") == (r,)


class TestBuildCatalog:
    def test_joins_repo_summary_and_classification(self):
        r = repo()
        s = Summary(r.full_name, "what it is", ("cli",), "h", "m")
        c = Classification(r.full_name, "cat", ("alt",), 0.9)
        entries = build_catalog([r], {r.full_name: s}, {r.full_name: c})
        assert len(entries) == 1
        assert entries[0].summary.summary == "what it is"
        assert entries[0].classification.primary == "cat"

    def test_tolerates_missing_summary_and_classification(self):
        entries = build_catalog([repo()], {}, {})
        assert entries[0].summary is None
        assert entries[0].classification is None

    def test_orders_by_starred_at_descending(self):
        old = repo("a/old", starred_at="2020-01-01T00:00:00Z")
        new = repo("b/new", starred_at="2026-01-01T00:00:00Z")
        entries = build_catalog([old, new], {}, {})
        assert [e.repo.full_name for e in entries] == ["b/new", "a/old"]

    def test_does_not_mutate_inputs(self):
        repos = [repo()]
        build_catalog(repos, {}, {})
        assert len(repos) == 1


def test_written_files_are_world_readable(tmp_path):
    """mkstemp creates 0600 files; served/committed data must be 0644."""
    p = write_json(tmp_path / "x.json", {"a": 1})
    assert p.stat().st_mode & 0o777 == 0o644
