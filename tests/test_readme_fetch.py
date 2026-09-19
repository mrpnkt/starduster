"""README batching over GraphQL."""

import json

import pytest
import responses

from starduster.config import GITHUB_GRAPHQL_URL
from starduster.github.client import GraphQLClient, fetch_readmes


@responses.activate
def test_fetch_readmes_chunks_and_maps_by_alias():
    def reply(request):
        body = json.loads(request.body)
        n = sum(1 for k in body["variables"] if k.startswith("owner"))
        data = {"rateLimit": {"cost": 1, "remaining": 1}}
        for i in range(n):
            name = body["variables"][f"name{i}"]
            data[f"r{i}"] = None if name == "gone" else {
                "nameWithOwner": f"{body['variables'][f'owner{i}']}/{name}",
                "readme_0": None, "readme_1": {"text": f"readme of {name}"}}
        return 200, {}, json.dumps({"data": data})

    responses.add_callback(responses.POST, GITHUB_GRAPHQL_URL, callback=reply)
    client = GraphQLClient(token="t", sleep=lambda _s: None)
    out = fetch_readmes(client, ["a/one", "b/two", "c/gone"], page_size=2)
    assert len(responses.calls) == 2, "3 repos at page size 2 = 2 requests"
    assert out == {"a/one": "readme of one", "b/two": "readme of two"}


def test_missing_token_fails_with_actionable_message():
    from starduster.github.client import GitHubError
    with pytest.raises(GitHubError, match="read:user"):
        GraphQLClient(token="")
