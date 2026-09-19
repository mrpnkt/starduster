import { test } from "node:test";
import assert from "node:assert/strict";
import { applyView, sample, selectResults, sortRecords, REDISCOVER_COUNT } from "../../web/js/core/filters.js";
import { emptyFilters, toggleFilter } from "../../web/js/core/facets.js";
import { DEFAULT_STATE, withState } from "../../web/js/core/url-state.js";
import { rec } from "./fixtures.js";

const TODAY = new Date("2026-09-19T00:00:00Z");

test("graveyard keeps only archived and dormant repos", () => {
  const R = ["active", "stale", "dormant", "archived"].map((m) => rec(`o/${m}`, { maintenance: m }));
  assert.deepEqual(applyView(R, "graveyard").map((r) => r.maintenance), ["dormant", "archived"]);
});

test("rediscover only draws repos starred at least two years ago", () => {
  const R = [rec("o/new", { starred_year: "2026" }), rec("o/mid", { starred_year: "2025" }),
             rec("o/old", { starred_year: "2024" }), rec("o/older", { starred_year: "2019" })];
  const names = applyView(R, "rediscover", { seed: 7, today: TODAY }).map((r) => r.name).sort();
  assert.deepEqual(names, ["o/old", "o/older"]);
});

test("rediscover is capped and reproducible from its seed", () => {
  const R = Array.from({ length: 100 }, (_, i) => rec(`o/${i}`, { starred_year: "2018" }));
  const a = applyView(R, "rediscover", { seed: 42, today: TODAY });
  const b = applyView(R, "rediscover", { seed: 42, today: TODAY });
  const c = applyView(R, "rediscover", { seed: 43, today: TODAY });
  assert.equal(a.length, REDISCOVER_COUNT);
  assert.deepEqual(a, b);
  assert.notDeepEqual(a, c);
});

test("sample does not mutate its input and has no duplicates", () => {
  const items = [1, 2, 3, 4, 5];
  const out = sample(items, 5, 3);
  assert.deepEqual(items, [1, 2, 3, 4, 5]);
  assert.equal(new Set(out).size, 5);
});

test("sortRecords does not mutate and sorts by stars", () => {
  const R = [rec("a/1", { stars: 5 }), rec("b/2", { stars: 50 })];
  const sorted = sortRecords(R, "stars_desc");
  assert.deepEqual(sorted.map((r) => r.name), ["b/2", "a/1"]);
  assert.deepEqual(R.map((r) => r.name), ["a/1", "b/2"]);
});

test("relevance uses search scores when present", () => {
  const R = [rec("a/1"), rec("b/2")];
  const scores = new Map([["a/1", 1], ["b/2", 9]]);
  assert.deepEqual(sortRecords(R, "relevance", scores).map((r) => r.name), ["b/2", "a/1"]);
});

test("relevance without a query falls back to recently starred", () => {
  const R = [rec("a/old", { starred: "2020-01-01" }), rec("b/new", { starred: "2026-01-01" })];
  assert.deepEqual(sortRecords(R, "relevance", null).map((r) => r.name), ["b/new", "a/old"]);
});

test("unknown sort key falls back safely", () => {
  assert.equal(sortRecords([rec("a/1")], "bogus").length, 1);
});

test("selectResults: search narrows the facet base, facets narrow results", () => {
  const R = [rec("a/go", { language: "Go" }), rec("b/rust", { language: "Rust" }), rec("c/py")];
  const scores = new Map([["a/go", 2], ["b/rust", 1]]);
  const state = withState(DEFAULT_STATE, { filters: toggleFilter(emptyFilters(), "language", "Go") });
  const { base, results } = selectResults(R, state, scores);
  assert.deepEqual(base.map((r) => r.name).sort(), ["a/go", "b/rust"]);
  assert.deepEqual(results.map((r) => r.name), ["a/go"]);
});

test("like view shows the repo then its neighbours in similarity order", () => {
  const R = [rec("a/1", { similar: [2, 1] }), rec("b/2"), rec("c/3"), rec("d/4")];
  const state = withState(DEFAULT_STATE, { like: "a/1", sort: "stars_desc" });
  const { results } = selectResults(R, state, null);
  assert.deepEqual(results.map((r) => r.name), ["a/1", "c/3", "b/2"], "sort is ignored");
});

test("like view still honours facets", () => {
  const R = [rec("a/1", { similar: [1, 2] }), rec("b/2", { language: "Go" }), rec("c/3")];
  const state = withState(DEFAULT_STATE, { like: "a/1", filters: toggleFilter(emptyFilters(), "language", "Go") });
  assert.deepEqual(selectResults(R, state, null).results.map((r) => r.name), ["b/2"]);
});

test("like with an unknown repo yields nothing rather than everything", () => {
  const state = withState(DEFAULT_STATE, { like: "nope/x" });
  assert.equal(selectResults([rec("a/1")], state, null).results.length, 0);
});
