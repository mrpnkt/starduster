"""Browser smoke test of the static site against a small fixture catalog."""

import json
import shutil

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from starduster.config import WEB_DIR  # noqa: E402
from starduster.serve import serve_in_background  # noqa: E402

TAXONOMY = {
    "version": "t1",
    "groups": [{"id": "dev", "name": "Developer tools"}],
    "categories": [
        {"id": "cli-tools", "name": "CLI tools", "parent": "dev", "definition": "", "disambiguation": ""},
        {"id": "web-apps", "name": "Web apps", "parent": "dev", "definition": "", "disambiguation": ""},
    ],
}


def record(name, **over):
    base = {
        "name": name, "description": "", "summary": "", "labels": [], "topics": [],
        "category": "cli-tools", "secondary": [], "confidence": 0.9,
        "language": "Python", "stars": 10, "stars_bucket": "<100",
        "maintenance": "active", "pushed": "2026-01-01", "starred": "2025-01-01",
        "starred_year": "2025",
    }
    base.update(over)
    return base


REPOS = [
    record("alice/ratelimiter", summary="A token-bucket rate limiter for HTTP clients.",
           language="Go", topics=["throttling"], similar=[2]),
    record("bob/webthing", summary="A self-hosted bookmark manager.", category="web-apps",
           language="TypeScript", maintenance="dormant"),
    record("eve/xss", description='<img src=x onerror="window.__pwned=1">', language="Rust",
           maintenance="archived"),
]


@pytest.fixture(scope="module")
def site_url(tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    shutil.copytree(WEB_DIR, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns("data"))
    (root / "data").mkdir()
    payload = {
        "meta": {"generated_at": "2026-09-19T00:00:00Z", "total": 3, "unclassified": 0,
                 "untagged": 2, "unsummarized": 1},
        "taxonomy": TAXONOMY,
        "repos": REPOS,
    }
    (root / "data" / "repos.json").write_text(json.dumps(payload))

    server, url = serve_in_background(root)
    yield url
    server.shutdown()


def count(page):
    return page.locator("#result-count strong")


def test_loads_and_shows_every_repo(page, site_url):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(site_url)
    expect(count(page)).to_have_text("3")
    expect(page.locator("#corpus-meta")).to_contain_text("2 with no GitHub topics")
    assert errors == []


def test_search_narrows_results_and_updates_url(page, site_url):
    page.goto(site_url)
    page.fill("#search", "bookmark")
    expect(count(page)).to_have_text("1")
    expect(page.locator(".row__name")).to_contain_text("webthing")
    assert "q=bookmark" in page.url


def test_category_facet_filters(page, site_url):
    page.goto(site_url)
    page.locator(".opt", has_text="Web apps").locator("input").check()
    expect(count(page)).to_have_text("1")
    expect(page.locator(".chip")).to_contain_text("Category: Web apps")


def test_deep_link_restores_state(page, site_url):
    page.goto(site_url + "?lang=Go")
    expect(count(page)).to_have_text("1")
    expect(page.locator(".opt", has_text="Go").locator("input")).to_be_checked()


def test_graveyard_view_shows_dead_repos(page, site_url):
    page.goto(site_url)
    page.click("[data-view=graveyard]")
    expect(count(page)).to_have_text("2")


def test_clicking_a_row_tag_applies_filter(page, site_url):
    page.goto(site_url)
    page.locator(".row", has_text="ratelimiter").locator("button.tag", has_text="Go").click()
    expect(count(page)).to_have_text("1")


def test_third_party_markup_is_rendered_as_text(page, site_url):
    page.goto(site_url)
    expect(page.locator(".row", has_text="eve/")).to_contain_text("<img src=x")
    assert page.evaluate("window.__pwned") is None


def test_summary_line_is_actually_visible(page, site_url):
    """Regression: flex shrink once collapsed every summary to zero height."""
    page.goto(site_url)
    summary = page.locator(".row", has_text="ratelimiter").locator(".row__summary")
    expect(summary).to_be_visible()
    assert summary.bounding_box()["height"] >= 14


def test_sort_control_shows_a_selection(page, site_url):
    page.goto(site_url)
    assert page.eval_on_selector("#sort", "s => s.selectedIndex") >= 0
    expect(page.locator("#sort")).to_have_value("relevance")


def test_similar_view_lists_neighbours_and_is_linkable(page, site_url):
    page.goto(site_url)
    page.locator(".row", has_text="ratelimiter").locator("button.tag--similar").click()
    expect(count(page)).to_have_text("2")
    expect(page.locator(".chip")).to_contain_text("Similar to alice/ratelimiter")
    assert "like=alice%2Fratelimiter" in page.url
    page.goto(site_url + "?like=alice/ratelimiter")
    expect(count(page)).to_have_text("2")
    page.locator(".chip button").click()
    expect(count(page)).to_have_text("3")
