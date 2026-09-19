// Result selection: view -> search -> facets -> sort. Pure.

import { matchesFacets } from "./facets.js";

export const VIEWS = Object.freeze(["all", "graveyard", "rediscover"]);

// Rediscover: things starred long enough ago to have been forgotten.
export const REDISCOVER_MIN_AGE_YEARS = 2;
export const REDISCOVER_COUNT = 15;

const DEAD = new Set(["archived", "dormant"]);

/** Deterministic PRNG so a Rediscover draw is reproducible from its URL. */
export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Seeded sample without replacement; does not mutate `items`. */
export function sample(items, count, seed) {
  const rand = mulberry32(seed);
  const pool = [...items];
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, count);
}

export function applyView(records, view, { seed = 1, today = new Date() } = {}) {
  if (view === "graveyard") {
    return records.filter((r) => DEAD.has(r.maintenance));
  }
  if (view === "rediscover") {
    const cutoff = today.getUTCFullYear() - REDISCOVER_MIN_AGE_YEARS;
    const old = records.filter((r) => Number(r.starred_year) <= cutoff);
    return sample(old, REDISCOVER_COUNT, seed);
  }
  return records;
}

const COMPARATORS = Object.freeze({
  starred_desc: (a, b) => b.starred.localeCompare(a.starred),
  starred_asc: (a, b) => a.starred.localeCompare(b.starred),
  stars_desc: (a, b) => b.stars - a.stars,
  stars_asc: (a, b) => a.stars - b.stars,
  pushed_desc: (a, b) => b.pushed.localeCompare(a.pushed),
  pushed_asc: (a, b) => a.pushed.localeCompare(b.pushed),
  name_asc: (a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }),
});

export const SORTS = Object.freeze(["relevance", ...Object.keys(COMPARATORS)]);

/**
 * Sort without mutating. "relevance" ranks by search score when a query is
 * active and falls back to most-recently-starred otherwise.
 */
export function sortRecords(records, sort, scores = null) {
  const copy = [...records];
  if (sort === "relevance") {
    if (scores) return copy.sort((a, b) => (scores.get(b.name) || 0) - (scores.get(a.name) || 0));
    return copy.sort(COMPARATORS.starred_desc);
  }
  return copy.sort(COMPARATORS[sort] || COMPARATORS.starred_desc);
}

/**
 * Full pipeline. `scores` is a Map(name -> score) of search hits, or null when
 * there is no query. Returns `{ base, results }`: `base` is the set facet
 * counts are computed over (view + search, before facets).
 */
/** The `like` repo followed by its precomputed neighbours, most similar first. */
export function similarTo(records, name) {
  const anchor = records.find((r) => r.name === name);
  if (!anchor) return [];
  return [anchor, ...(anchor.similar || []).map((i) => records[i]).filter(Boolean)];
}

export function selectResults(records, state, scores, opts = {}) {
  if (state.like) {
    // Similarity order is the point of this view, so search and sort are ignored.
    const base = similarTo(records, state.like);
    return { base, results: base.filter((r) => matchesFacets(r, state.filters)) };
  }
  const viewed = applyView(records, state.view, { seed: state.seed, ...opts });
  const base = scores ? viewed.filter((r) => scores.has(r.name)) : viewed;
  const filtered = base.filter((r) => matchesFacets(r, state.filters));
  return { base, results: sortRecords(filtered, state.sort, scores) };
}
