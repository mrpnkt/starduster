"""Loading and saving the committed pipeline state under `data/`."""

from __future__ import annotations

from .. import config
from ..models import Repo, Summary, Taxonomy
from ..taxonomy import parse_taxonomy
from .failures import Failure, ledger_from_dict, ledger_to_dict
from .io import read_json, write_json
from .serialize import repo_from_dict, repo_to_dict, summaries_from_dict, summaries_to_dict


def load_repos() -> tuple[Repo, ...]:
    return tuple(repo_from_dict(r) for r in read_json(config.RAW_STARS_PATH, default=[]))


def save_repos(repos: tuple[Repo, ...]) -> None:
    write_json(config.RAW_STARS_PATH, [repo_to_dict(r) for r in repos])


def load_summaries() -> dict[str, Summary]:
    return summaries_from_dict(read_json(config.SUMMARIES_PATH, default={}))


def save_summaries(items: dict[str, Summary]) -> None:
    write_json(config.SUMMARIES_PATH, summaries_to_dict(items))


def load_failures(stage: str) -> dict[str, Failure]:
    return ledger_from_dict((read_json(config.FAILURES_PATH, default={}) or {}).get(stage, {}))


def save_failures(stage: str, ledger: dict[str, Failure]) -> None:
    everything = read_json(config.FAILURES_PATH, default={}) or {}
    write_json(config.FAILURES_PATH, {**everything, stage: ledger_to_dict(ledger)})


def load_taxonomy() -> Taxonomy | None:
    data = read_json(config.TAXONOMY_PATH)
    return None if data is None else parse_taxonomy(data)
