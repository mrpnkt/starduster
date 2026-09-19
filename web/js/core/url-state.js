// App state <-> URL query string. Pure; every view is bookmarkable.

import { FACETS, emptyFilters } from "./facets.js";
import { SORTS, VIEWS } from "./filters.js";

export const DEFAULT_STATE = Object.freeze({
  q: "",
  view: "all",
  sort: "relevance",
  seed: 1,
  like: "",
  filters: emptyFilters(),
});

// GitHub owner/repo names: letters, digits, '-', '_', '.'.
const REPO_NAME = /^[A-Za-z0-9_.-]{1,100}\/[A-Za-z0-9_.-]{1,100}$/;

export function parseState(search) {
  const params = new URLSearchParams(search);
  const view = params.get("view");
  const sort = params.get("sort");
  const seed = Number.parseInt(params.get("seed") || "", 10);

  const filters = Object.fromEntries(
    FACETS.map((f) => [
      f.key,
      Object.freeze([...new Set(params.getAll(f.param).filter(Boolean))]),
    ]),
  );

  return Object.freeze({
    q: (params.get("q") || "").slice(0, 200),
    view: VIEWS.includes(view) ? view : DEFAULT_STATE.view,
    sort: SORTS.includes(sort) ? sort : DEFAULT_STATE.sort,
    seed: Number.isFinite(seed) && seed > 0 ? seed : DEFAULT_STATE.seed,
    like: REPO_NAME.test(params.get("like") || "") ? params.get("like") : "",
    filters: Object.freeze(filters),
  });
}

/** Serialize, omitting defaults so plain URLs stay plain. */
export function serializeState(state) {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.view !== DEFAULT_STATE.view) params.set("view", state.view);
  if (state.sort !== DEFAULT_STATE.sort) params.set("sort", state.sort);
  if (state.view === "rediscover") params.set("seed", String(state.seed));
  if (state.like) params.set("like", state.like);
  for (const facet of FACETS) {
    for (const value of state.filters[facet.key] || []) params.append(facet.param, value);
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export function withState(state, patch) {
  return Object.freeze({ ...state, ...patch });
}
