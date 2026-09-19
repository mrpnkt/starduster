"""Ollama HTTP client: embeddings, structured chat, and actionable errors."""

import json

import numpy as np
import pytest
import requests
import responses

from starduster.local.ollama import OllamaClient, OllamaError

URL = "http://ollama.test"


@pytest.fixture
def client():
    return OllamaClient(URL, sleep=lambda _s: None)


@responses.activate
def test_embed_batches_and_normalizes(client):
    def reply(request):
        n = len(json.loads(request.body)["input"])
        return 200, {}, json.dumps({"embeddings": [[3.0, 4.0]] * n})
    responses.add_callback(responses.POST, f"{URL}/api/embed", callback=reply)
    out = client.embed(["a", "b", "c"], model="m", batch_size=2)
    assert out.shape == (3, 2) and out.dtype == np.float32
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0)
    assert len(responses.calls) == 2


@responses.activate
def test_embed_empty_makes_no_call(client):
    assert client.embed([], model="m").shape == (0, 0)
    assert len(responses.calls) == 0


@responses.activate
def test_embed_count_mismatch_is_an_error(client):
    responses.add(responses.POST, f"{URL}/api/embed", json={"embeddings": [[1.0]]})
    with pytest.raises(OllamaError, match="expected 2"):
        client.embed(["a", "b"], model="m")


@responses.activate
def test_chat_json_passes_schema_and_parses(client):
    responses.add(responses.POST, f"{URL}/api/chat",
                  json={"message": {"content": '{"name": "X"}'}})
    assert client.chat_json("m", "prompt", {"type": "object"}) == {"name": "X"}
    body = json.loads(responses.calls[0].request.body)
    assert body["format"] == {"type": "object"} and body["stream"] is False
    assert body["options"]["temperature"] == 0


@responses.activate
def test_chat_json_garbage_raises(client):
    responses.add(responses.POST, f"{URL}/api/chat", json={"message": {"content": "nope"}})
    with pytest.raises(OllamaError, match="JSON"):
        client.chat_json("m", "p", {})


@responses.activate
def test_missing_model_tells_you_to_pull_it(client):
    responses.add(responses.POST, f"{URL}/api/embed", status=404,
                  json={"error": "model 'm' not found"})
    with pytest.raises(OllamaError, match="ollama pull m"):
        client.embed(["a"], model="m")


@responses.activate
def test_server_down_tells_you_to_start_it(client):
    responses.add(responses.POST, f"{URL}/api/embed", body=requests.ConnectionError("refused"))
    with pytest.raises(OllamaError, match="ollama serve"):
        client.embed(["a"], model="m")


@responses.activate
def test_transient_500_is_retried(client):
    responses.add(responses.POST, f"{URL}/api/embed", status=500)
    responses.add(responses.POST, f"{URL}/api/embed", json={"embeddings": [[1.0, 0.0]]})
    assert client.embed(["a"], model="m").shape == (1, 2)


@responses.activate
def test_model_digest(client):
    responses.add(responses.GET, f"{URL}/api/tags", json={"models": [
        {"name": "other:latest", "digest": "aaa"}, {"name": "m:v1", "digest": "bbb"}]})
    assert client.model_digest("m:v1") == "bbb"
    with pytest.raises(OllamaError, match="ollama pull nope"):
        client.model_digest("nope")


@responses.activate
def test_embed_reports_progress_per_batch(client):
    def reply(request):
        n = len(json.loads(request.body)["input"])
        return 200, {}, json.dumps({"embeddings": [[1.0, 0.0]] * n})
    responses.add_callback(responses.POST, f"{URL}/api/embed", callback=reply)
    seen = []
    client.embed(["a"] * 5, model="m", batch_size=2, on_batch=lambda done, total: seen.append((done, total)))
    assert seen == [(2, 5), (4, 5), (5, 5)]


@responses.activate
def test_timeout_is_retried_then_reported_with_the_limit():
    lines = []
    c = OllamaClient(URL, sleep=lambda _s: None, log=lines.append)
    for _ in range(3):
        responses.add(responses.POST, f"{URL}/api/embed", body=requests.ReadTimeout("slow"))
    with pytest.raises(OllamaError, match="did not answer"):
        c.embed(["a"], model="m")
    assert len(lines) == 2, "a line per retry"


def test_timeouts_are_bounded():
    from starduster import config
    connect, read = config.OLLAMA_TIMEOUT
    assert connect <= 10 and read <= 120
