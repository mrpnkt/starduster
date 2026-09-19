"""README cleaning and hard token caps — the main driver of per-repo cost."""

from starduster.tokens import cap_tokens, estimate_tokens
from starduster.github.readme import clean_readme, prepare_readme


class TestEstimate:
    def test_english_is_about_a_quarter_of_chars_rounded_up_conservatively(self):
        text = "The quick brown fox jumps over the lazy dog. " * 20  # 900 chars
        assert 225 <= estimate_tokens(text) <= 350

    def test_cjk_counts_every_character(self):
        """6,000 CJK chars is ~6,000 tokens, not ~1,500."""
        assert estimate_tokens("用户仓库" * 100) >= 400

    def test_empty(self):
        assert estimate_tokens("") == 0


class TestCap:
    def test_short_text_untouched(self):
        assert cap_tokens("hello world", 100) == "hello world"

    def test_english_capped_within_budget(self):
        out = cap_tokens("word " * 10_000, 500)
        assert estimate_tokens(out) <= 500

    def test_cjk_capped_within_budget(self):
        out = cap_tokens("仓" * 50_000, 500)
        assert estimate_tokens(out) <= 500
        assert len(out) <= 500

    def test_prefers_line_boundary(self):
        text = "a" * 1000 + "\n" + "b" * 1000
        out = cap_tokens(text, 400)
        assert out.endswith("a") and "b" not in out


class TestClean:
    def test_strips_html_images_badges_and_data_uris(self):
        raw = (
            '<p align="center"><img src="logo.png" width=200></p>\n'
            "[![CI](https://img.shields.io/badge/ci-passing-green)](https://ci)\n"
            "![screenshot](https://example.com/shot.png)\n"
            "![inline](data:image/png;base64," + "A" * 5000 + ")\n"
            "# Tool\n\nDoes a useful thing.\n"
        )
        out = clean_readme(raw)
        assert "Does a useful thing." in out and "# Tool" in out
        for junk in ("<img", "<p", "shields.io", "screenshot", "base64", "AAAA"):
            assert junk not in out

    def test_keeps_link_text_drops_url(self):
        assert clean_readme("See [the docs](https://x.y/very/long/path).") == "See the docs."

    def test_collapses_blank_runs(self):
        assert clean_readme("a\n\n\n\n\nb") == "a\n\nb"

    def test_drops_html_comments(self):
        assert clean_readme("a<!-- hidden\nstuff -->b") == "ab"


def test_prepare_readme_is_clean_then_capped():
    huge = "![b](https://img.shields.io/x)\n" * 2000 + "Real content. " * 20_000
    out = prepare_readme(huge, max_tokens=800)
    assert "shields" not in out
    assert out.startswith("Real content.")
    assert estimate_tokens(out) <= 800


def test_prompts_enforce_caps_even_on_oversized_stored_data():
    from starduster.local.prompts import render_repo
    from starduster.config import README_MAX_TOKENS
    from starduster.models import Repo
    r = Repo("o/n", "仓" * 5000, (), 1, None, None, "", "", False, False, "u", "仓" * 50_000)
    assert estimate_tokens(render_repo(r)) <= README_MAX_TOKENS + 250


def test_normalized_edges_store_capped_readmes():
    from starduster.config import README_MAX_TOKENS
    from starduster.github.normalize import normalize_edge
    edge = {"starredAt": "", "node": {"nameWithOwner": "o/n", "readme_0": {"text": "x " * 100_000}}}
    assert estimate_tokens(normalize_edge(edge).readme_excerpt) <= README_MAX_TOKENS


class TestSecretRedaction:
    """Third-party READMEs contain real and example credentials; never store them.

    GitHub push protection blocks pushes containing them, which would break the
    daily data commit, and republishing someone's leaked key is wrong anyway.
    """

    import pytest

    # Built at runtime: literal example secrets in source would themselves
    # trip GitHub push protection.
    @pytest.mark.parametrize("secret", [
        "https://hooks.slack" + ".com/services/" + "T00000000/B00000000/" + "X" * 24,
        "xox" + "b-123456789012-123456789012-" + "a" * 24,
        "gh" + "p_" + "a" * 36,
        "github" + "_pat_" + "A1" * 30,
        "AK" + "IA" + "IOSFODNN7" + "EXAMPLE",
        "AI" + "za" + "B" * 35,
        "https://discord" + ".com/api/webhooks/" + "1" * 18 + "/" + "t" * 68,
        "sk-" + "ant-api03-" + "x" * 40,
        "sk-" + "Y" * 48,
    ])
    def test_known_secret_formats_are_redacted(self, secret):
        out = clean_readme(f"Configure it with {secret} and run.")
        assert secret not in out
        assert "[redacted]" in out
        assert out.startswith("Configure it with") and out.endswith("and run.")

    def test_private_key_blocks_are_redacted(self):
        text = "Key:\n-----BEGIN RSA PRIVATE KEY-----\nMIIEow" + "A" * 200 + "\n-----END RSA PRIVATE KEY-----\ndone"
        out = clean_readme(text)
        assert "MIIEow" not in out and "[redacted]" in out and out.endswith("done")

    def test_ordinary_text_is_untouched(self):
        text = "Use sk-learn style APIs; see https://slack.com and ghp docs."
        assert clean_readme(text) == text
