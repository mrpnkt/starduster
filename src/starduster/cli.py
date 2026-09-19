"""Command-line entry point.

Daily, in GitHub Actions ($0):   fetch -> embed -> build      (`starduster all`)
Occasionally, on your machine:   taxonomy, summarize          (local Ollama)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Sequence

from . import config
from .build import build_payload
from .categorize.assign import assign_categories, categories_without_centre
from .categorize.centroids import load_centroids, save_centroids
from .categorize.embeddings import EmbeddingError, empty, load_embeddings, save_embeddings
from .categorize.probe import PROBE_TEXTS, ProbeError, check_probe
from .categorize.similar import similar_indices
from .categorize.text import embedding_text
from .github.client import GitHubError, GraphQLClient, fetch_readmes, fetch_stars
from .github.readme import prepare_readme
from .local.ollama import OllamaClient, OllamaError
from .local.summarize import summarize_local
from .models import Repo, Taxonomy
from .store.failures import record_attempts
from .store.io import read_json, write_json
from .store.keys import summary_hash, summary_version_key
from .store.merge import build_catalog, repos_needing_summary
from .store.repository import (
    load_failures,
    load_repos,
    load_summaries,
    load_taxonomy,
    save_failures,
    save_repos,
    save_summaries,
)
from .store.serialize import repo_from_dict, repo_to_dict
from .taxonomy import TaxonomyError, taxonomy_to_dict


def _github_client() -> GraphQLClient:
    return GraphQLClient(token=os.environ.get("GITHUB_TOKEN") or os.environ.get("STARS_TOKEN") or "")


def _ollama() -> OllamaClient:
    return OllamaClient()


# --- fetch ------------------------------------------------------------------------


def _attach_readmes(client: GraphQLClient, repos: tuple[Repo, ...]) -> tuple[Repo, ...]:
    """Carry READMEs forward; fetch them only for repos never seen before.

    Repos without a README are "seen" too, so they are not re-queried daily.
    Carried excerpts are re-prepared, bringing older data within current caps.
    """
    previous = {r.full_name: r for r in load_repos()}
    repos = tuple(
        r.with_readme(prepare_readme(previous[r.full_name].readme_excerpt))
        if r.full_name in previous else r
        for r in repos
    )
    new = [r.full_name for r in repos if r.full_name not in previous]
    if not new:
        return repos
    print(f"Fetching READMEs for {len(new)} new repos...")
    try:
        readmes = fetch_readmes(client, new)
    except GitHubError as exc:
        print(f"README fetch failed ({exc}); continuing without them.", file=sys.stderr)
        return repos
    return tuple(r.with_readme(readmes[r.full_name]) if r.full_name in readmes else r for r in repos)


def cmd_fetch(args: argparse.Namespace) -> int:
    """Page the GitHub API, resuming from a checkpoint if one exists."""
    client = _github_client()
    checkpoint = {} if args.restart else (read_json(config.FETCH_CHECKPOINT_PATH, default={}) or {})
    collected = tuple(repo_from_dict(r) for r in checkpoint.get("repos", []))
    if collected:
        print(f"Resuming from checkpoint: {len(collected)} repos already fetched")

    def on_page(repos, cursor):
        write_json(config.FETCH_CHECKPOINT_PATH,
                   {"cursor": cursor, "repos": [repo_to_dict(r) for r in repos]})
        print(f"  {len(repos)} repos fetched", end="\r", flush=True)

    try:
        repos, total = fetch_stars(client, cursor=checkpoint.get("cursor"),
                                   collected=collected, on_page=on_page)
    except GitHubError as exc:
        print(f"\nFetch failed: {exc}\nCheckpoint kept; re-run `fetch` to resume.", file=sys.stderr)
        return 1

    print(f"\nFetched {len(repos)} of {total} starred repos")
    if not args.skip_readmes:
        repos = _attach_readmes(client, repos)
    save_repos(repos)
    config.FETCH_CHECKPOINT_PATH.unlink(missing_ok=True)
    return 0


# --- embed ------------------------------------------------------------------------


def cmd_embed(args: argparse.Namespace) -> int:
    """Embed repos that have no vector yet (all of them with --rebuild)."""
    repos = load_repos()
    if not repos:
        raise SystemExit("No repos. Run `starduster fetch` first.")
    ollama = _ollama()
    try:
        digest = ollama.model_digest(config.EMBED_MODEL)
        es = empty(digest) if args.rebuild else load_embeddings(config.EMBEDDINGS_PATH)
        probe = ollama.embed(PROBE_TEXTS, model=config.EMBED_MODEL)
        if es.probe is not None:
            worst = check_probe(es.probe, probe, config.PROBE_MIN_SIMILARITY)
            print(f"Embedding parity check passed (worst probe similarity {worst:.4f})")
        else:
            es = es.with_probe(probe)

        todo = es.missing(repos)
        if not todo:
            print("All repos already embedded.")
            save_embeddings(config.EMBEDDINGS_PATH, es)
            return 0
        print(f"Embedding {len(todo)} repo(s) with {config.EMBED_MODEL}...")
        vectors = ollama.embed([embedding_text(r) for r in todo], model=config.EMBED_MODEL)
        es = es.with_added(tuple(r.full_name for r in todo), vectors, digest=digest)
    except (OllamaError, ProbeError, EmbeddingError) as exc:
        print(f"Embedding failed: {exc}", file=sys.stderr)
        return 1
    save_embeddings(config.EMBEDDINGS_PATH, es)
    print(f"Wrote {len(es.names)} embeddings to {config.EMBEDDINGS_PATH}")
    return 0


# --- taxonomy (local) -------------------------------------------------------------


def cmd_taxonomy(args: argparse.Namespace) -> int:
    """Cluster all embeddings and name the clusters with the local LLM."""
    from .categorize.bootstrap import bootstrap_taxonomy

    if read_json(config.TAXONOMY_PATH) is not None and not args.force:
        print(f"{config.TAXONOMY_PATH} exists. Edit it by hand, or pass --force to "
              "regenerate it (your edits would be lost).", file=sys.stderr)
        return 2
    repos = {r.full_name: r for r in load_repos()}
    es = load_embeddings(config.EMBEDDINGS_PATH)
    if len(es.names) < args.clusters:
        raise SystemExit("Too few embeddings. Run `starduster embed` first.")
    if len(es.missing(list(repos.values()))):
        print("Warning: some repos are not embedded yet; run `starduster embed` first "
              "for the best clusters.", file=sys.stderr)

    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    try:
        taxonomy, centroids = bootstrap_taxonomy(
            es, repos, _ollama(), k=args.clusters, model=args.model, version=version)
    except (OllamaError, TaxonomyError) as exc:
        print(f"Taxonomy failed: {exc}", file=sys.stderr)
        return 1
    write_json(config.TAXONOMY_PATH, taxonomy_to_dict(taxonomy))
    save_centroids(config.CENTROIDS_PATH, centroids)
    print(f"Wrote {config.TAXONOMY_PATH} ({len(taxonomy.categories)} categories). "
          "Review and edit it, then `starduster build`.")
    return 0


# --- summarize (local) ------------------------------------------------------------


def cmd_summarize(args: argparse.Namespace) -> int:
    """One-line summaries from the local LLM. Each repo is done once."""
    repos = load_repos()
    cached = load_summaries()
    failures = load_failures("summary")
    pv = config.PROMPT_VERSION
    todo = repos_needing_summary(repos, cached, pv, failures=failures)
    if args.limit:
        todo = todo[: args.limit]
    if not todo:
        print("All summaries current.")
        return 0

    print(f"Summarizing {len(todo)} repo(s) with {args.model} (Ctrl+C is safe; progress is saved)")

    def save(done):
        save_summaries({**cached, **done})

    try:
        done = summarize_local(_ollama(), todo, model=args.model, prompt_version=pv, on_progress=save)
    except KeyboardInterrupt:
        print("\nStopped; progress so far is saved.")
        return 130
    except OllamaError as exc:
        print(f"Summarize failed: {exc}", file=sys.stderr)
        return 1
    save_failures("summary", record_attempts(
        failures, todo, set(done), summary_version_key(pv), lambda r: summary_hash(r, pv)))
    print(f"Summarized {len(done)}; {len(todo) - len(done)} failed this attempt")
    return 0


# --- build ------------------------------------------------------------------------


def _categorize(taxonomy: Taxonomy | None, es, neighbours):
    centroids = load_centroids(config.CENTROIDS_PATH)
    if taxonomy is None or centroids is None:
        return {}
    orphans = categories_without_centre(taxonomy, centroids, es)
    if orphans:
        print(f"Warning: categories with no centre (add `seeds`): {', '.join(orphans)}",
              file=sys.stderr)
    return assign_categories(es, centroids, taxonomy, neighbours=neighbours)


def cmd_build(args: argparse.Namespace) -> int:
    """Join repos, summaries, categories and similar repos into the site payload."""
    repos = load_repos()
    if not repos:
        raise SystemExit("No repos. Run `starduster fetch` first.")
    taxonomy = load_taxonomy()
    es = load_embeddings(config.EMBEDDINGS_PATH)
    rows = similar_indices(es.vectors) if es.names else []
    similar = {es.names[i]: [es.names[j] for j in row] for i, row in enumerate(rows)}
    classifications = _categorize(taxonomy, es, rows)

    entries = build_catalog(repos, load_summaries(), classifications)
    payload = build_payload(entries, taxonomy or Taxonomy("none", (), ()), similar=similar)
    out = config.WEB_DATA_DIR / "repos.json"
    write_json(out, payload, compact=True)
    meta = payload["meta"]
    print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KB, {meta['total']} repos, "
          f"{meta['unclassified']} unsorted)")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .serve import make_server

    server = make_server(config.WEB_DIR, port=args.port, quiet=False)
    print(f"Serving http://127.0.0.1:{args.port}/ (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    """The daily CI pipeline. Uses no LLM, only the embedding model."""
    for step in (cmd_fetch, cmd_embed, cmd_build):
        code = step(args)
        if code:
            return code
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="starduster",
                                     description="A categorized catalog of your GitHub stars.")
    parser.set_defaults(force=False, limit=0, restart=False, skip_readmes=False, rebuild=False,
                        model=config.LLM_MODEL, clusters=config.TAXONOMY_CLUSTERS, port=8000)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch", help="fetch starred repos from GitHub")
    p.add_argument("--restart", action="store_true", help="ignore any checkpoint")
    p.add_argument("--skip-readmes", action="store_true")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("embed", help="embed new repos with the local embedding model")
    p.add_argument("--rebuild", action="store_true", help="re-embed every repo")
    p.set_defaults(func=cmd_embed)

    p = sub.add_parser("taxonomy", help="cluster + name categories (local LLM)")
    p.add_argument("--clusters", type=int, default=config.TAXONOMY_CLUSTERS)
    p.add_argument("--model", default=config.LLM_MODEL)
    p.add_argument("--force", action="store_true", help="overwrite an existing taxonomy")
    p.set_defaults(func=cmd_taxonomy)

    p = sub.add_parser("summarize", help="one-line summaries (local LLM, optional)")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--model", default=config.LLM_MODEL)
    p.set_defaults(func=cmd_summarize)

    sub.add_parser("build", help="emit the static site payload").set_defaults(func=cmd_build)

    p = sub.add_parser("serve", help="preview the site locally")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    sub.add_parser("all", help="fetch, embed, build (the daily pipeline)").set_defaults(func=cmd_all)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
