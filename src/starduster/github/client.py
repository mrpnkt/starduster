"""GitHub GraphQL transport and star pagination.

The retry policy here is not defensive boilerplate: probing the live endpoint
produced an nginx `502 Bad Gateway` (an HTML body, not JSON) that survived six
retries across ~30 seconds before clearing. Hence a long backoff, and a
checkpoint callback so an interrupted local fetch resumes instead of
restarting. (In CI the checkpoint is not carried between runs: a failed
fetch costs only GraphQL points, ~70 requests, never money.)
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping, NamedTuple, Sequence

import requests

from ..config import (
    BACKOFF_INITIAL_SECONDS,
    BACKOFF_MAX_SECONDS,
    GITHUB_GRAPHQL_URL,
    MAX_ATTEMPTS,
    RATE_LIMIT_MAX_WAIT_SECONDS,
    README_PAGE_SIZE,
    STARS_PAGE_SIZE,
)
from ..models import Repo
from .normalize import normalize_edges, pick_readme
from .readme import prepare_readme
from .query import STARS_QUERY, readme_query

# Retrying these cannot help: the request or credentials are wrong. A 403 is
# the exception when it carries rate-limit signals (see `_rate_limit_wait`).
_FATAL_STATUSES = frozenset({400, 401, 403, 404, 422})

CheckpointHook = Callable[[tuple[Repo, ...], str | None], None]


class GitHubError(RuntimeError):
    """A GraphQL request failed in a way retrying did not fix."""


class _Retry(NamedTuple):
    """A transient failure: why, and how long GitHub asked us to wait (if said)."""

    reason: str
    wait: float | None = None


def _rate_limit_wait(response: requests.Response) -> _Retry | None:
    """Recognise GitHub's rate limiting, which arrives as 429 or as a 403.

    Returns None when the response is not a rate limit.
    """
    status = response.status_code
    headers = response.headers
    text = response.text.lower()
    limited = status == 429 or (
        status == 403
        and (
            "retry-after" in headers
            or headers.get("x-ratelimit-remaining") == "0"
            or "rate limit" in text
        )
    )
    if not limited:
        return None

    wait: float | None = None
    try:
        if "retry-after" in headers:
            wait = float(headers["retry-after"])
        elif "x-ratelimit-reset" in headers:
            wait = max(0.0, float(headers["x-ratelimit-reset"]) - time.time())
    except ValueError:
        wait = None
    if wait is not None:
        wait = min(wait, RATE_LIMIT_MAX_WAIT_SECONDS)
    return _Retry(f"rate limited (HTTP {status})", wait)


class GraphQLClient:
    """Thin GraphQL caller with bounded exponential backoff.

    `sleep` is injected so tests exercise the retry ladder without waiting.
    """

    def __init__(
        self,
        token: str,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not token:
            raise GitHubError(
                "No GitHub token. Set GITHUB_TOKEN to a PAT with read:user "
                "scope — note that Actions' default GITHUB_TOKEN belongs to "
                "github-actions[bot], which has no stars."
            )
        self._token = token
        self._session = session or requests.Session()
        self._sleep = sleep
        self.rate_limit_remaining: int | None = None

    def execute(self, query: str, variables: Mapping[str, Any]) -> dict[str, Any]:
        """Run a query, retrying transient failures. Returns the `data` block."""
        delay = BACKOFF_INITIAL_SECONDS
        last = _Retry("unknown error")

        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                self._sleep(last.wait if last.wait is not None else delay)
                delay = min(delay * 2, BACKOFF_MAX_SECONDS)

            outcome = self._attempt(query, variables)
            if not isinstance(outcome, _Retry):
                return outcome
            last = outcome

        raise GitHubError(
            f"Giving up after {MAX_ATTEMPTS} attempts. Last problem: {last.reason}"
        )

    def _attempt(
        self, query: str, variables: Mapping[str, Any]
    ) -> dict[str, Any] | _Retry:
        """One request. Returns data, a `_Retry`, or raises on fatal errors."""
        try:
            response = self._session.post(
                GITHUB_GRAPHQL_URL,
                json={"query": query, "variables": dict(variables)},
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                },
                timeout=60,
            )
        except requests.RequestException as exc:
            return _Retry(f"network error: {exc}")

        limited = _rate_limit_wait(response)
        if limited:
            return limited

        if response.status_code in _FATAL_STATUSES:
            raise GitHubError(
                f"HTTP {response.status_code} from GitHub "
                f"(not retryable): {response.text[:200]}"
            )
        if response.status_code >= 500:
            # Body is nginx HTML here, so never attempt to parse it.
            return _Retry(f"HTTP {response.status_code} from GitHub")

        try:
            payload = response.json()
        except ValueError:
            return _Retry(f"non-JSON body: {response.text[:200]}")

        errors = payload.get("errors") or []
        if any(e.get("type") == "RATE_LIMITED" for e in errors):
            return _Retry("GraphQL RATE_LIMITED")
        if errors:
            messages = "; ".join(e.get("message", "?") for e in errors)
            raise GitHubError(f"GraphQL errors: {messages}")

        data = payload.get("data")
        if data is None:
            return _Retry("GraphQL returned null data with no errors")

        self._record_rate_limit(data)
        return data

    def _record_rate_limit(self, data: Mapping[str, Any]) -> None:
        limit = data.get("rateLimit")
        if isinstance(limit, Mapping) and "remaining" in limit:
            self.rate_limit_remaining = limit["remaining"]


def fetch_stars(
    client: GraphQLClient,
    *,
    cursor: str | None = None,
    collected: Sequence[Repo] = (),
    on_page: CheckpointHook | None = None,
    page_size: int = STARS_PAGE_SIZE,
) -> tuple[tuple[Repo, ...], int]:
    """Page through the viewer's stars.

    Returns `(repos, total_count)`. `collected` and `cursor` together allow a
    resumed run to continue from a checkpoint; `on_page` is called after every
    page so the caller can persist that checkpoint.
    """
    repos: tuple[Repo, ...] = tuple(collected)
    total = len(repos)

    while True:
        data = client.execute(
            STARS_QUERY, {"pageSize": page_size, "cursor": cursor}
        )
        starred = data["viewer"]["starredRepositories"]
        total = starred.get("totalCount", total)

        # Re-dedupe across the whole accumulation, not just this page: a
        # resumed fetch can legitimately overlap the checkpoint boundary.
        known = {r.full_name for r in repos}
        fresh = tuple(
            r for r in normalize_edges(starred["edges"]) if r.full_name not in known
        )
        repos = repos + fresh

        page_info = starred["pageInfo"]
        cursor = page_info.get("endCursor")

        if on_page:
            on_page(repos, cursor)

        if not page_info.get("hasNextPage"):
            return repos, total


def fetch_readmes(
    client: GraphQLClient,
    full_names: Sequence[str],
    *,
    page_size: int = README_PAGE_SIZE,
) -> dict[str, str]:
    """Fetch README excerpts for specific repos, keyed by full name.

    Batched by `page_size` because blobs are heavy; a whole-corpus README pull
    at the star-listing page size is what provoked repeated 502s.
    """
    out: dict[str, str] = {}

    for start in range(0, len(full_names), page_size):
        chunk = list(full_names[start : start + page_size])
        variables: dict[str, Any] = {}
        for i, full_name in enumerate(chunk):
            owner, _, name = full_name.partition("/")
            variables[f"owner{i}"] = owner
            variables[f"name{i}"] = name

        data = client.execute(readme_query(len(chunk)), variables)

        for i, full_name in enumerate(chunk):
            node = data.get(f"r{i}")
            if not isinstance(node, Mapping):
                continue  # repo deleted or went private since the star listing
            out[full_name] = prepare_readme(pick_readme(node))

    return out
