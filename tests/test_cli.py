"""CLI wiring against a fake Ollama and temp data paths."""

import hashlib

import numpy as np
import pytest

from starduster import cli, config
from starduster.local.ollama import OllamaError
from starduster.models import Repo
from starduster.store.io import read_json, write_json
from starduster.store.serialize import repo_from_dict, repo_to_dict


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    for name, filename in [
        ("RAW_STARS_PATH", "raw-stars.json"), ("SUMMARIES_PATH", "summaries.json"),
        ("TAXONOMY_PATH", "taxonomy.json"), ("FETCH_CHECKPOINT_PATH", ".ckpt.json"),
        ("FAILURES_PATH", "failures.json"), ("EMBEDDINGS_PATH", "embeddings.npz"),
        ("CENTROIDS_PATH", "centroids.npz"),
    ]:
        monkeypatch.setattr(config, name, tmp_path / filename)
    monkeypatch.setattr(config, "WEB_DATA_DIR", tmp_path / "web")
    return tmp_path


class FakeOllama:
    def __init__(self, digest="d1", fail_chat=False, drift=0.0):
        self.digest, self.fail_chat, self.drift = digest, fail_chat, drift
        self.embedded, self.chats = [], 0

    def model_digest(self, model):
        return self.digest

    def embed(self, texts, *, model, on_batch=None):
        self.embedded.extend(texts)
        rows = []
        for t in texts:
            seed = int(hashlib.md5(t.encode()).hexdigest()[:8], 16)
            v = np.random.default_rng(seed).normal(size=16)
            v[0] += self.drift * 50
            rows.append(v / np.linalg.norm(v))
        return np.asarray(rows, dtype=np.float32)

    def chat_json(self, model, prompt, schema, **kw):
        self.chats += 1
        if self.fail_chat:
            raise OllamaError("bad json")
        return {"summary": "A thing.", "labels": ["cli"]}


def repo(name):
    return Repo(name, "d", ("t",), 5, "Go", "MIT", "2026-01-01T00:00:00Z",
                "2025-01-01T00:00:00Z", False, False, f"https://github.com/{name}", "r")


def seed_repos(n):
    write_json(config.RAW_STARS_PATH, [repo_to_dict(repo(f"o/r{i}")) for i in range(n)])


def use(monkeypatch, fake):
    monkeypatch.setattr(cli, "_ollama", lambda: fake)
    return fake


def test_repo_round_trips_through_json():
    assert repo_from_dict(repo_to_dict(repo("a/b"))) == repo("a/b")


class TestEmbed:
    def test_embeds_only_new_repos(self, data_dir, monkeypatch):
        seed_repos(3)
        use(monkeypatch, FakeOllama())
        assert cli.main(["embed"]) == 0
        seed_repos(5)
        fake = use(monkeypatch, FakeOllama())
        assert cli.main(["embed"]) == 0
        repo_texts = [t for t in fake.embedded if "o/r" in t]
        assert len(repo_texts) == 2

    def test_parity_probe_drift_stops_the_run(self, data_dir, monkeypatch, capsys):
        seed_repos(2)
        use(monkeypatch, FakeOllama())
        cli.main(["embed"])
        use(monkeypatch, FakeOllama(drift=1.0))
        assert cli.main(["embed"]) == 1
        assert "re-embed" in capsys.readouterr().err

    def test_model_change_refuses_to_mix_vectors(self, data_dir, monkeypatch, capsys):
        seed_repos(2)
        use(monkeypatch, FakeOllama(digest="d1"))
        cli.main(["embed"])
        seed_repos(3)
        use(monkeypatch, FakeOllama(digest="d2"))
        assert cli.main(["embed"]) == 1
        assert "digest" in capsys.readouterr().err

    def test_rebuild_reembeds_everything(self, data_dir, monkeypatch):
        seed_repos(3)
        use(monkeypatch, FakeOllama())
        cli.main(["embed"])
        fake = use(monkeypatch, FakeOllama(digest="d2"))
        assert cli.main(["embed", "--rebuild"]) == 0
        assert len([t for t in fake.embedded if "o/r" in t]) == 3


class TestSummarize:
    def test_summarizes_and_saves(self, data_dir, monkeypatch):
        seed_repos(2)
        use(monkeypatch, FakeOllama())
        assert cli.main(["summarize"]) == 0
        assert set(read_json(config.SUMMARIES_PATH)) == {"o/r0", "o/r1"}

    def test_done_repos_are_not_redone(self, data_dir, monkeypatch):
        seed_repos(2)
        use(monkeypatch, FakeOllama())
        cli.main(["summarize"])
        fake = use(monkeypatch, FakeOllama())
        cli.main(["summarize"])
        assert fake.chats == 0

    def test_failed_repos_stop_being_retried(self, data_dir, monkeypatch):
        seed_repos(1)
        calls = []
        for _ in range(3):
            fake = use(monkeypatch, FakeOllama(fail_chat=True))
            cli.main(["summarize"])
            calls.append(fake.chats)
        assert calls == [1, 1, 0]

    def test_limit(self, data_dir, monkeypatch):
        seed_repos(5)
        fake = use(monkeypatch, FakeOllama())
        cli.main(["summarize", "--limit", "2"])
        assert fake.chats == 2


def test_taxonomy_will_not_overwrite_without_force(data_dir, monkeypatch):
    seed_repos(1)
    write_json(config.TAXONOMY_PATH, {"version": "hand-edited"})
    use(monkeypatch, FakeOllama())
    assert cli.main(["taxonomy"]) == 2
    assert read_json(config.TAXONOMY_PATH)["version"] == "hand-edited"


class TestBuild:
    def test_works_before_any_taxonomy_exists(self, data_dir):
        seed_repos(2)
        assert cli.main(["build"]) == 0
        payload = read_json(config.WEB_DATA_DIR / "repos.json")
        assert payload["meta"]["total"] == 2 and payload["meta"]["unclassified"] == 2


def test_full_local_flow(data_dir, monkeypatch):
    """fetch output -> embed -> taxonomy -> build, end to end with fakes."""
    seed_repos(12)
    use(monkeypatch, FakeOllama())
    assert cli.main(["embed"]) == 0
    assert cli.main(["taxonomy", "--clusters", "3"]) == 0
    tax = read_json(config.TAXONOMY_PATH)
    assert len(tax["categories"]) == 3
    assert cli.main(["build"]) == 0
    payload = read_json(config.WEB_DATA_DIR / "repos.json")
    assert all(len(r["similar"]) == config.SIMILAR_REPOS for r in payload["repos"])


def test_readmes_fetched_only_for_never_seen_repos(data_dir, monkeypatch):
    """Repos seen before (with or without a README) are not re-queried daily."""
    write_json(config.RAW_STARS_PATH, [repo_to_dict(repo("o/known")),
                                       repo_to_dict(repo("o/no-readme").with_readme(""))])
    fetched = []
    monkeypatch.setattr(cli, "fetch_readmes",
                        lambda client, names: fetched.extend(names) or {"o/new": "new readme"})
    listing = (repo("o/known").with_readme(""), repo("o/no-readme").with_readme(""),
               repo("o/new").with_readme(""))
    out = {r.full_name: r for r in cli._attach_readmes(object(), listing)}
    assert fetched == ["o/new"]
    assert out["o/known"].readme_excerpt == "r"
    assert out["o/new"].readme_excerpt == "new readme"
