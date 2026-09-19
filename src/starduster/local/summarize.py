"""Optional one-line summaries from a local LLM (`starduster summarize`).

Free but slow (measure with `--limit 20`; roughly 5-10s per repo on an
M1 Max with llama3.2:3b), so progress is
handed back every `save_every` repos and an interrupted run loses little.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from ..config import MAX_TOKENS_SUMMARY, SUMMARY_SAVE_EVERY
from ..models import Repo, Summary
from ..store.keys import summary_hash, summary_version_key
from .ollama import OllamaError
from .prompts import SUMMARY_SYSTEM, render_repo
from .schema import SUMMARY_SCHEMA

SUMMARY_MAX_CHARS = 240


def _to_summary(repo: Repo, reply: dict[str, Any], model: str, prompt_version: str) -> Summary | None:
    text = str(reply.get("summary") or "").strip()[:SUMMARY_MAX_CHARS]
    if not text:
        return None
    return Summary(
        full_name=repo.full_name,
        summary=text,
        # A 3B model tagged nearly everything "cli, library, self-hostable";
        # misleading labels are worse than none, so the local pass omits them.
        labels=(),
        input_hash=summary_hash(repo, prompt_version),
        model=model,
        version_key=summary_version_key(prompt_version),
    )


def summarize_local(
    llm: Any,
    repos: Sequence[Repo],
    *,
    model: str,
    prompt_version: str,
    save_every: int = SUMMARY_SAVE_EVERY,
    on_progress: Callable[[dict[str, Summary]], None] | None = None,
    log=print,
) -> dict[str, Summary]:
    done: dict[str, Summary] = {}
    for i, repo in enumerate(repos, 1):
        try:
            reply = llm.chat_json(model, render_repo(repo), SUMMARY_SCHEMA,
                                  system=SUMMARY_SYSTEM, max_tokens=MAX_TOKENS_SUMMARY)
            summary = _to_summary(repo, reply, model, prompt_version)
            if summary:
                done = {**done, repo.full_name: summary}
        except OllamaError as exc:
            log(f"  {repo.full_name}: {exc}")
        if on_progress and (i % save_every == 0 or i == len(repos)):
            on_progress(done)
            log(f"  {i}/{len(repos)} summarized")
    return done
