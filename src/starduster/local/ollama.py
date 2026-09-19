"""Minimal Ollama HTTP client: embeddings and schema-constrained chat.

Errors are rewritten into the command that fixes them ("ollama serve",
"ollama pull <model>"), because the usual failure is a stopped server or a
model that was never pulled, not a bug.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import requests

from ..config import EMBED_BATCH_SIZE, OLLAMA_TIMEOUT_SECONDS, OLLAMA_URL

_RETRIES = 3


class OllamaError(RuntimeError):
    """Ollama could not do what was asked; the message says how to fix it."""


class OllamaClient:
    def __init__(
        self,
        base_url: str = OLLAMA_URL,
        *,
        timeout: float = OLLAMA_TIMEOUT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._url = base_url.rstrip("/")
        self._timeout = timeout
        self._sleep = sleep
        self._session = requests.Session()

    def _request(self, method: str, path: str, model: str = "", **kwargs) -> Any:
        last = ""
        for attempt in range(_RETRIES):
            if attempt:
                self._sleep(2.0 * attempt)
            try:
                resp = self._session.request(
                    method, f"{self._url}{path}", timeout=self._timeout, **kwargs
                )
            except requests.ConnectionError as exc:
                raise OllamaError(
                    f"Cannot reach Ollama at {self._url} ({exc}). Start it with "
                    "`ollama serve` (or open the Ollama app)."
                ) from exc
            except requests.RequestException as exc:
                last = str(exc)
                continue
            if resp.status_code == 404 and "not found" in resp.text:
                raise OllamaError(
                    f"Model {model!r} is not installed. Run `ollama pull {model}`."
                )
            if resp.status_code >= 500:
                last = f"HTTP {resp.status_code}: {resp.text[:200]}"
                continue
            if resp.status_code >= 400:
                raise OllamaError(f"Ollama {path} failed: HTTP {resp.status_code}: {resp.text[:200]}")
            return resp.json()
        raise OllamaError(f"Ollama {path} failed after {_RETRIES} attempts: {last}")

    def embed(
        self, texts: Sequence[str], *, model: str, batch_size: int = EMBED_BATCH_SIZE
    ) -> np.ndarray:
        """Embed texts; returns unit-length float32 rows (cosine = dot product)."""
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        rows: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            chunk = list(texts[start : start + batch_size])
            data = self._request(
                "POST", "/api/embed", model, json={"model": model, "input": chunk, "truncate": True}
            )
            got = data.get("embeddings") or []
            if len(got) != len(chunk):
                raise OllamaError(f"Ollama returned {len(got)} embeddings, expected {len(chunk)}")
            rows.extend(got)
        matrix = np.asarray(rows, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.where(norms == 0, 1.0, norms)

    def chat_json(
        self, model: str, prompt: str, schema: Mapping[str, Any], *, system: str = "",
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """One structured-output chat turn, parsed. Deterministic (temperature 0)."""
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        options: dict[str, Any] = {"temperature": 0}
        if max_tokens:
            options["num_predict"] = max_tokens
        data = self._request(
            "POST", "/api/chat", model,
            json={"model": model, "messages": messages, "stream": False,
                  "format": dict(schema), "options": options},
        )
        content = (data.get("message") or {}).get("content", "")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"{model} did not return valid JSON: {content[:120]!r}") from exc
        if not isinstance(parsed, dict):
            raise OllamaError(f"{model} returned JSON that is not an object")
        return parsed

    def model_digest(self, model: str) -> str:
        """Content digest of an installed model; pins which weights made a vector."""
        for entry in self._request("GET", "/api/tags").get("models", []):
            if entry.get("name") == model or entry.get("model") == model:
                return entry.get("digest", "")
        raise OllamaError(f"Model {model!r} is not installed. Run `ollama pull {model}`.")
