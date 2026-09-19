"""Transport resilience: the 502s, retry budget, and cursor checkpointing."""

import json

import pytest
import responses

from starduster.config import GITHUB_GRAPHQL_URL
from starduster.github.client import (
    GitHubError,
    GraphQLClient,
    fetch_stars,
)

BAD_GATEWAY_HTML = (
    "<html>\n<head><title>502 Bad Gateway</title></head>\n"
    "<body><center><h1>502 Bad Gateway</h1></center></body>\n</html>\n"
)


def stars_page(names, has_next, cursor="CUR"):
    return {
        "data": {
            "rateLimit": {"cost": 1, "remaining": 4999},
            "viewer": {
                "starredRepositories": {
                    "totalCount": 99,
                    "pageInfo": {"endCursor": cursor, "hasNextPage": has_next},
                    "edges": [
                        {
                            "starredAt": "2025-01-01T00:00:00Z",
                            "node": {
                                "nameWithOwner": n,
                                "description": "d",
                                "url": f"https://github.com/{n}",
                                "stargazerCount": 1,
                                "pushedAt": "2026-01-01T00:00:00Z",
                                "isArchived": False,
                                "isFork": False,
                                "primaryLanguage": None,
                                "licenseInfo": None,
                                "repositoryTopics": {"nodes": []},
                            },
                        }
                        for n in names
                    ],
                }
            },
        }
    }


@pytest.fixture
def client():
    # No real sleeping in tests.
    return GraphQLClient(token="t", sleep=lambda _s: None)


class TestRetry:
    @responses.activate
    def test_recovers_from_a_transient_502(self, client):
        """Observed live: page 0 succeeded, page 1 502'd, then cleared."""
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      body=BAD_GATEWAY_HTML, status=502)
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json=stars_page(["a/b"], False))
        data = client.execute("query{x}", {})
        assert data["viewer"]["starredRepositories"]["totalCount"] == 99
        assert len(responses.calls) == 2

    @responses.activate
    def test_html_error_body_does_not_raise_json_decode_error(self, client):
        """The 502 body is nginx HTML, not JSON."""
        for _ in range(12):
            responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                          body=BAD_GATEWAY_HTML, status=502)
        with pytest.raises(GitHubError) as exc:
            client.execute("query{x}", {})
        assert "502" in str(exc.value)

    @responses.activate
    def test_gives_up_after_max_attempts(self, client):
        for _ in range(12):
            responses.add(responses.POST, GITHUB_GRAPHQL_URL, status=500)
        with pytest.raises(GitHubError):
            client.execute("query{x}", {})
        from starduster.config import MAX_ATTEMPTS
        assert len(responses.calls) == MAX_ATTEMPTS

    @responses.activate
    def test_backoff_grows_and_is_capped(self):
        slept = []
        c = GraphQLClient(token="t", sleep=slept.append)
        for _ in range(12):
            responses.add(responses.POST, GITHUB_GRAPHQL_URL, status=502)
        with pytest.raises(GitHubError):
            c.execute("query{x}", {})
        from starduster.config import BACKOFF_MAX_SECONDS
        assert slept == sorted(slept), "delays must be non-decreasing"
        assert max(slept) <= BACKOFF_MAX_SECONDS
        assert slept[1] > slept[0]

    @responses.activate
    def test_does_not_retry_unauthorized(self, client):
        """A bad token will never succeed; failing fast beats 9 attempts."""
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json={"message": "Bad credentials"}, status=401)
        with pytest.raises(GitHubError):
            client.execute("query{x}", {})
        assert len(responses.calls) == 1

    @responses.activate
    def test_graphql_errors_payload_raises(self, client):
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json={"errors": [{"message": "bad field"}]})
        with pytest.raises(GitHubError) as exc:
            client.execute("query{x}", {})
        assert "bad field" in str(exc.value)

    @responses.activate
    def test_retries_when_data_is_null_but_no_error_given(self, client):
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, json={"data": None})
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json=stars_page(["a/b"], False))
        assert client.execute("query{x}", {}) is not None

    @responses.activate
    def test_sends_bearer_token(self, client):
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json=stars_page(["a/b"], False))
        client.execute("query{x}", {})
        assert responses.calls[0].request.headers["Authorization"] == "Bearer t"


class TestFetchStars:
    @responses.activate
    def test_pages_until_exhausted(self, client):
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json=stars_page(["a/1"], True, "C1"))
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json=stars_page(["b/2"], True, "C2"))
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json=stars_page(["c/3"], False, "C3"))
        repos, _ = fetch_stars(client)
        assert [r.full_name for r in repos] == ["a/1", "b/2", "c/3"]

    @responses.activate
    def test_forwards_cursor_to_next_page(self, client):
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json=stars_page(["a/1"], True, "CURSOR_A"))
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json=stars_page(["b/2"], False, "CURSOR_B"))
        fetch_stars(client)
        second = json.loads(responses.calls[1].request.body)
        assert second["variables"]["cursor"] == "CURSOR_A"

    @responses.activate
    def test_resumes_from_a_checkpoint(self, client):
        """Resuming must not refetch the pages already collected."""
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json=stars_page(["c/3"], False, "C3"))
        existing = stars_page(["a/1"], True)["data"]["viewer"]
        from starduster.github.normalize import normalize_edges
        prior = normalize_edges(existing["starredRepositories"]["edges"])
        repos, _ = fetch_stars(client, cursor="C1", collected=prior)
        assert [r.full_name for r in repos] == ["a/1", "c/3"]
        first = json.loads(responses.calls[0].request.body)
        assert first["variables"]["cursor"] == "C1"

    @responses.activate
    def test_invokes_checkpoint_callback_per_page(self, client):
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json=stars_page(["a/1"], True, "C1"))
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json=stars_page(["b/2"], False, "C2"))
        seen = []
        fetch_stars(client, on_page=lambda repos, cur: seen.append((len(repos), cur)))
        assert seen == [(1, "C1"), (2, "C2")]

    @responses.activate
    def test_returns_total_count(self, client):
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json=stars_page(["a/1"], False))
        _, total = fetch_stars(client)
        assert total == 99


class TestRateLimits:
    """GitHub signals rate limiting several ways; all are transient."""

    @responses.activate
    def test_secondary_rate_limit_403_is_retried_honouring_retry_after(self):
        slept = []
        c = GraphQLClient(token="t", sleep=slept.append)
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, status=403,
                      headers={"Retry-After": "7"},
                      json={"message": "You have exceeded a secondary rate limit."})
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, json=stars_page(["a/b"], False))
        assert c.execute("query{x}", {})
        assert slept == [7]

    @responses.activate
    def test_rate_limit_message_without_header_is_retried(self, client):
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, status=403,
                      json={"message": "API rate limit exceeded for user."})
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, json=stars_page(["a/b"], False))
        assert client.execute("query{x}", {})

    @responses.activate
    def test_429_is_retried(self, client):
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, status=429)
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, json=stars_page(["a/b"], False))
        assert client.execute("query{x}", {})

    @responses.activate
    def test_graphql_rate_limited_error_is_retried(self, client):
        responses.add(responses.POST, GITHUB_GRAPHQL_URL,
                      json={"errors": [{"type": "RATE_LIMITED", "message": "slow down"}]})
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, json=stars_page(["a/b"], False))
        assert client.execute("query{x}", {})

    @responses.activate
    def test_plain_permission_403_still_fails_fast(self, client):
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, status=403,
                      json={"message": "Resource not accessible by integration"})
        with pytest.raises(GitHubError):
            client.execute("query{x}", {})
        assert len(responses.calls) == 1

    @responses.activate
    def test_retry_after_is_capped(self):
        slept = []
        c = GraphQLClient(token="t", sleep=slept.append)
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, status=429,
                      headers={"Retry-After": "99999"})
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, json=stars_page(["a/b"], False))
        c.execute("query{x}", {})
        from starduster.config import RATE_LIMIT_MAX_WAIT_SECONDS
        assert slept == [RATE_LIMIT_MAX_WAIT_SECONDS]


class TestRetryVisibility:
    """Silent backoff made a 12-minute fetch look like a hang in CI."""

    @responses.activate
    def test_each_retry_is_logged_with_reason_and_wait(self):
        lines = []
        c = GraphQLClient(token="t", sleep=lambda _s: None, log=lines.append)
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, status=502)
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, json=stars_page(["a/b"], False))
        c.execute("query{x}", {})
        assert len(lines) == 1
        assert "502" in lines[0] and "retrying in" in lines[0] and "attempt 2/" in lines[0]

    @responses.activate
    def test_success_logs_nothing(self):
        lines = []
        c = GraphQLClient(token="t", sleep=lambda _s: None, log=lines.append)
        responses.add(responses.POST, GITHUB_GRAPHQL_URL, json=stars_page(["a/b"], False))
        c.execute("query{x}", {})
        assert lines == []
