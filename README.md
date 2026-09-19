# starduster

An always-on, browsable catalog of your GitHub stars. Every repo gets a
category, including the half that have no GitHub topics. **Runs for $0**: no
paid APIs, only local models via [Ollama](https://ollama.com).

In the collection this was built for, **1,674 of 3,267 starred repos (51%)
had no topics**, and the rest used 5,030 distinct topics, 3,599 of them only
once. Starduster reads each repo's README, embeds it with a small local model,
and files it into categories derived from *your* collection.

## How it works

| Where | Command | What it does |
|---|---|---|
| GitHub Actions, daily | `starduster fetch` | Pages your stars via GraphQL (retries, resumable). Fetches READMEs only for repos it has never seen; READMEs are stripped of badges/HTML/images and capped at a hard token limit. |
| GitHub Actions, daily | `starduster embed` | Embeds **only new** repos with `nomic-embed-text` (Ollama, on the runner's CPU). Each repo is embedded once. |
| GitHub Actions, daily | `starduster build` | Assigns every repo to its nearest category, finds its 10 most similar repos, writes the site. Deterministic: nothing is ever "reclassified". |
| Your Mac, once | `starduster taxonomy` | Clusters all embeddings (35 groups) and has a local LLM name them. You then edit `data/taxonomy.json`. |
| Your Mac, optional | `starduster summarize` | One-line "what is this" summaries from a local LLM. ~6.5 s/repo with `llama3.2:3b` on an M1 Max (≈6 h for 3,267 repos; Ctrl+C is safe and resumable). Each repo is summarized once. |

### The site

- Search, facets with live counts: category, maintenance (active / stale / dormant / archived), language, year starred, popularity, has-topics
- **≈ similar** on every repo: its 10 nearest neighbours by README content
- **Suggested topics** (`≈#topic`, dashed) on repos with no GitHub topics: topics that
  at least 3 of its 10 most similar tagged repos share, drawn only from topics you
  already use. Clicking any topic finds real and suggested matches. Measured on
  held-out tagged repos: 62% got at least one exact match and 47% of specific
  suggestions matched exactly; this beat local LLMs (`llama3.2:3b`, `qwen2.5:7b`)
  on precision at zero cost
- **Graveyard**: archived or no commits in 2+ years, for pruning. **Rediscover**: random old stars
- Every view is a shareable URL; light/dark; mobile

## Setup

### 1. Create a token that can read your stars

GitHub Actions' built-in token belongs to a bot account with no stars, so the
workflow needs a token of **your** account.

1. Go to **GitHub → Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token**
   (direct link: https://github.com/settings/personal-access-tokens/new).
2. **Token name**: `starduster`. **Expiration**: the longest allowed (you will
   need to repeat these steps when it expires; the workflow run will fail with
   an HTTP 401 when that happens).
3. **Repository access**: *Public repositories* (read-only).
4. **Permissions → Account permissions → Starring**: *Read-only*.
   Nothing else is needed.
5. **Generate token** and copy it (it starts with `github_pat_`). GitHub shows
   it only once.

### 2. Store it as a repository secret

1. Open **this** repository on GitHub → **Settings** (repo settings, not your
   profile) → **Secrets and variables → Actions**.
2. **New repository secret**. **Name**: `STARS_TOKEN` (exactly). **Secret**:
   paste the token. **Add secret**.

That is the only secret. There is no API key and nothing that costs money.

### 3. Turn on GitHub Pages

**Settings → Pages → Build and deployment → Source: GitHub Actions**. (Not
"Deploy from a branch".)

### 4. Build the taxonomy once, on your Mac

```bash
ollama pull nomic-embed-text:v1.5 && ollama pull llama3.2:3b
python3 -m venv .venv && .venv/bin/pip install -e ".[local]"
export GITHUB_TOKEN=$(gh auth token)      # or the token from step 1

.venv/bin/starduster fetch                # ~3 min
.venv/bin/starduster embed                # ~3 min
.venv/bin/starduster taxonomy             # ~2 min, writes data/taxonomy.json
# edit data/taxonomy.json (see below), then preview:
.venv/bin/starduster build && .venv/bin/starduster serve   # http://127.0.0.1:8000

git add data && git commit -m "data: initial taxonomy" && git push
```

### 5. Run the workflow

The push triggers **Actions → Refresh stars** automatically; afterwards it
runs daily at 05:17 UTC. To run it by hand: **Actions → Refresh stars → Run
workflow**. When it finishes, the site URL is shown on the run's **deploy**
job (usually `https://<you>.github.io/starduster/`).

## Editing categories

`data/taxonomy.json` is yours to edit, locally or directly on github.com
(saving it there triggers a rebuild). Nothing needs reprocessing afterwards.

- **Rename / redefine**: change `name` or `definition`.
- **Regroup**: change a category's `parent` to another group `id`.
- **Merge**: delete a category; its repos move to their nearest remaining one.
- **Add or split**: add a category with `"seeds": ["owner/repo", ...]`; its
  centre is the average of those repos.
- **Fix one repo**: `"pins": {"owner/repo": "category-id"}` always wins.

Different names: `starduster taxonomy --force --model <model>` uses another
local model (e.g. `qwen2.5:14b` after `ollama pull qwen2.5:14b`). Larger models
generally name more precisely than `llama3.2:3b`, but this has not been
benchmarked here. Note `--force` overwrites your hand edits.

### Accuracy, honestly

Categories are nearest-centre assignments in embedding space, corrected when a
repo's neighbours clearly agree on a different category (this changed 2.2% of
repos, nearly all for the better). On held-out repos, 94% land in the same
category the clustering gave them. In a collection dominated by one theme,
roughly a third of repos sit between two neighbouring categories where either
is defensible. Use `pins` for the ones that matter to you.

## Costs

$0. The daily job embeds only new stars (seconds of CPU). The failure ledger
means a repo the local model cannot summarize is tried at most twice, then left
alone.

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m playwright install chromium   # once, for browser tests
.venv/bin/pytest --cov=starduster                 # unit, integration, E2E
npm test                                          # frontend logic (node:test)
```
