"""Central configuration. No hardcoded values elsewhere in the package."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

# --- Paths -------------------------------------------------------------------

# The checkout being operated on: the working directory, or STARDUSTER_ROOT.
# Never derived from __file__: after a regular `pip install .` that points into
# site-packages, and CI silently ran against an empty data directory.
ROOT: Final[Path] = Path(os.environ.get("STARDUSTER_ROOT") or Path.cwd()).resolve()
DATA_DIR: Final[Path] = ROOT / "data"
WEB_DIR: Final[Path] = ROOT / "web"
WEB_DATA_DIR: Final[Path] = WEB_DIR / "data"

RAW_STARS_PATH: Final[Path] = DATA_DIR / "raw-stars.json"
FETCH_CHECKPOINT_PATH: Final[Path] = DATA_DIR / ".fetch-checkpoint.json"
TAXONOMY_PATH: Final[Path] = DATA_DIR / "taxonomy.json"
SUMMARIES_PATH: Final[Path] = DATA_DIR / "summaries.json"
EMBEDDINGS_PATH: Final[Path] = DATA_DIR / "embeddings.npz"
CENTROIDS_PATH: Final[Path] = DATA_DIR / "centroids.npz"
FAILURES_PATH: Final[Path] = DATA_DIR / "failures.json"

# --- GitHub ------------------------------------------------------------------

GITHUB_GRAPHQL_URL: Final[str] = "https://api.github.com/graphql"

# Page size 50, not 100: heavier per-node selections at 100/page provoked
# repeated HTTP 502s from the GraphQL endpoint during probing.
STARS_PAGE_SIZE: Final[int] = 50

# READMEs are blobs; they need a smaller page than plain metadata.
README_PAGE_SIZE: Final[int] = 25

# A 502 was observed surviving six retries over ~30s before clearing, so the
# backoff has to reach into the tens of seconds before giving up.
MAX_ATTEMPTS: Final[int] = 9
BACKOFF_INITIAL_SECONDS: Final[float] = 2.0
BACKOFF_MAX_SECONDS: Final[float] = 60.0

# Upper bound on honouring a Retry-After / rate-limit reset from GitHub.
RATE_LIMIT_MAX_WAIT_SECONDS: Final[float] = 300.0

# README filenames vary across repos; these are tried as aliased GraphQL fields.
README_PATHS: Final[tuple[str, ...]] = (
    "README.md",
    "README",
    "readme.md",
    "README.rst",
    "README.txt",
    "docs/README.md",
)

# Hard caps on README input, in *estimated tokens* (see tokens.py, which
# over-counts on purpose). A character cap would let CJK READMEs cost 4x more.
README_MAX_TOKENS: Final[int] = 1200       # stored, and sent to Pass A
README_CLASSIFY_TOKENS: Final[int] = 300   # Pass C already has the summary

# --- Local models (Ollama) -----------------------------------------------------
#
# Everything runs locally for $0. The embedding model also runs in GitHub
# Actions on CPU for the daily handful of new stars; the generative model is
# only used on your machine (taxonomy naming, optional summaries).

OLLAMA_URL: Final[str] = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
EMBED_MODEL: Final[str] = "nomic-embed-text:v1.5"
LLM_MODEL: Final[str] = os.environ.get("STARDUSTER_LLM", "llama3.2:3b")
# (connect, read) seconds per request. A stalled server fails a step in
# minutes instead of silently holding it (the first CI run hung for 15+ min).
OLLAMA_TIMEOUT: Final[tuple[float, float]] = (10.0, 120.0)
EMBED_BATCH_SIZE: Final[int] = 32

# nomic-embed-text expects a task prefix; "clustering: " suits grouping.
EMBED_PREFIX: Final[str] = "clustering: "
# README share of the embedded text, in estimated tokens (well inside the
# model's 2,048-token context once name, description and topics are added).
EMBED_README_TOKENS: Final[int] = 600

# --- Categorization ------------------------------------------------------------

# Clusters proposed by `starduster taxonomy`. Measured on this collection:
# k=35 gives a largest cluster of 5% and a smallest of 24 repos.
TAXONOMY_CLUSTERS: Final[int] = 35
TAXONOMY_EXAMPLES_PER_CLUSTER: Final[int] = 15

# A repo whose best cosine similarity to any category centre is below this is
# left "unsorted" rather than forced into a poor fit. 0.78 is the 1st
# percentile of member-to-centre similarity measured on this collection.
UNSORTED_SIMILARITY: Final[float] = 0.78
# A second category is shown when it is nearly as close as the first. Measured
# best-vs-second margins: 10th percentile 0.005, median 0.016.
SECONDARY_MARGIN: Final[float] = 0.005

SIMILAR_REPOS: Final[int] = 10

# Category centres are averages; in a collection dominated by one theme the
# big centres sit close to everything and can win for outliers. If at least
# this share of a repo's nearest neighbours (similarity-weighted) agree on a
# different category, theirs wins. Measured: 60% changes 2.2% of repos, and a
# sample of those changes was clearly better; lower thresholds (kNN outright)
# moved 36% of repos with mixed results.
NEIGHBOUR_CONSENSUS: Final[float] = 0.6

# Embeddings from CI (Linux, CPU) must match the ones made on your Mac, or new
# stars would be compared in a slightly different vector space. Probe texts are
# embedded on both and must agree to this cosine similarity.
PROBE_MIN_SIMILARITY: Final[float] = 0.995

# --- Suggested topics ----------------------------------------------------------
#
# Repos with no GitHub topics borrow them from their most similar tagged repos.
# Measured on 50 held-out tagged repos (topics hidden, re-embedded without them):
# 62% got at least one exact match; 47% of specific suggestions were exact
# matches (more were reasonable). Beat llama3.2:3b and qwen2.5:7b on precision.
SUGGEST_NEIGHBOURS: Final[int] = 10
SUGGEST_MIN_VOTES: Final[int] = 3
SUGGEST_MAX_TOPICS: Final[int] = 5
SUGGEST_MIN_TOPIC_USES: Final[int] = 3   # only topics you already use repeatedly
SUGGEST_STOP_TOPICS: Final[tuple[str, ...]] = ("hacktoberfest",)

# --- Summaries (local LLM, optional) --------------------------------------------

MAX_TOKENS_SUMMARY: Final[int] = 120
# README share of a summary prompt. Prompt size dominates local speed: at
# 1,200 tokens llama3.2:3b took ~9.8s/repo on an M1 Max.
SUMMARY_README_TOKENS: Final[int] = 600
SUMMARY_SAVE_EVERY: Final[int] = 25  # long local runs checkpoint as they go

# Bump to regenerate every summary on purpose.
PROMPT_VERSION: Final[str] = "1"

# When False (default) a summarized repo is never redone because its
# maintainer edited the description; only a PROMPT_VERSION bump redoes it.
REPROCESS_ON_CONTENT_CHANGE: Final[bool] = False

# A repo the local model fails on (unparseable output) is tried at most this
# many times per prompt version, then left alone.
MAX_ATTEMPTS_PER_REPO: Final[int] = 2

# --- Derived facets ----------------------------------------------------------

MAINTENANCE_ACTIVE_DAYS: Final[int] = 183
MAINTENANCE_STALE_DAYS: Final[int] = 730

STAR_BUCKETS: Final[tuple[tuple[str, int], ...]] = (
    ("50k+", 50_000),
    ("10k-50k", 10_000),
    ("1k-10k", 1_000),
    ("100-1k", 100),
    ("<100", 0),
)
