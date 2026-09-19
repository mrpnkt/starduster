"""Every repo is paid for once. Nothing is retried daily."""

from starduster.store.keys import summary_hash, summary_version_key
from starduster.models import Repo, Summary
from starduster.store.failures import Failure, record_attempts
from starduster.store.merge import repos_needing_summary


def repo(name="o/n", **over):
    base = dict(full_name=name, description="d", topics=(), stars=1, language=None,
                license=None, pushed_at="", starred_at="", is_archived=False,
                is_fork=False, url="u", readme_excerpt="r")
    base.update(over)
    return Repo(**base)


def summary_for(r, pv="1"):
    return Summary(r.full_name, "s", (), summary_hash(r, pv), "m", summary_version_key(pv))


class TestContentChangesDoNotReprocessByDefault:
    def test_description_edit_does_not_resummarize(self):
        cached = {"o/n": summary_for(repo())}
        edited = repo(description="maintainer rewrote the tagline")
        assert repos_needing_summary([edited], cached, "1") == ()

    def test_opt_in_reprocesses_on_content_change(self):
        cached = {"o/n": summary_for(repo())}
        edited = repo(description="new")
        assert repos_needing_summary([edited], cached, "1", reprocess_on_change=True) == (edited,)

    def test_prompt_version_bump_still_reprocesses(self):
        cached = {"o/n": summary_for(repo())}
        assert repos_needing_summary([repo()], cached, "2") == (repo(),)


class TestFailureLedger:
    def test_repo_is_retried_until_attempts_exhausted_then_left_alone(self):
        r = repo()
        ledger = {}
        for _ in range(2):
            assert repos_needing_summary([r], {}, "1", failures=ledger) == (r,)
            ledger = record_attempts(ledger, [r], succeeded=set(), version_key=summary_version_key("1"),
                                     hash_of=lambda x: summary_hash(x, "1"))
        assert repos_needing_summary([r], {}, "1", failures=ledger) == ()

    def test_success_clears_the_ledger_entry(self):
        r = repo()
        ledger = record_attempts({}, [r], set(), summary_version_key("1"), lambda x: "h")
        ledger = record_attempts(ledger, [r], {"o/n"}, summary_version_key("1"), lambda x: "h")
        assert ledger == {}

    def test_version_bump_gives_failed_repos_a_fresh_chance(self):
        r = repo()
        ledger = {}
        for _ in range(2):
            ledger = record_attempts(ledger, [r], set(), summary_version_key("1"), lambda x: summary_hash(x, "1"))
        assert repos_needing_summary([r], {}, "2", failures=ledger) == (r,)

    def test_ledger_does_not_mutate_input(self):
        before = {}
        record_attempts(before, [repo()], set(), "k", lambda x: "h")
        assert before == {}

    def test_attempts_increment(self):
        led = record_attempts({}, [repo()], set(), "k", lambda x: "h")
        led = record_attempts(led, [repo()], set(), "k", lambda x: "h")
        assert led["o/n"] == Failure("o/n", "h", "k", 2)
