import { test } from "node:test";
import assert from "node:assert/strict";
import { countFacets, emptyFilters, matchesFacets, toggleFilter } from "../../web/js/core/facets.js";
import { rec } from "./fixtures.js";

const R = [
  rec("a/go", { language: "Go", category: "cli-tools" }),
  rec("b/rust", { language: "Rust", category: "cli-tools" }),
  rec("c/py", { language: "Python", category: "web-apps", topics: ["x"] }),
];

test("no filters matches everything", () => {
  assert.ok(R.every((r) => matchesFacets(r, emptyFilters())));
});

test("options within a facet are OR-ed", () => {
  const f = toggleFilter(toggleFilter(emptyFilters(), "language", "Go"), "language", "Rust");
  assert.deepEqual(R.filter((r) => matchesFacets(r, f)).map((r) => r.name), ["a/go", "b/rust"]);
});

test("facets are AND-ed together", () => {
  let f = toggleFilter(emptyFilters(), "language", "Python");
  f = toggleFilter(f, "category", "cli-tools");
  assert.equal(R.filter((r) => matchesFacets(r, f)).length, 0);
});

test("a facet's counts ignore its own selection", () => {
  const f = toggleFilter(emptyFilters(), "language", "Go");
  const counts = countFacets(R, f);
  assert.equal(counts.language.get("Rust"), 1, "Rust stays clickable");
  assert.equal(counts.category.get("cli-tools"), 1, "other facets are narrowed");
  assert.equal(counts.category.get("web-apps"), undefined);
});

test("untagged repos are countable", () => {
  assert.equal(countFacets(R, emptyFilters()).topics_state.get("none"), 2);
});

test("missing category and language map to a none bucket", () => {
  const counts = countFacets([rec("x/y", { category: null, language: null })], emptyFilters());
  assert.equal(counts.category.get("__none"), 1);
  assert.equal(counts.language.get("__none"), 1);
});

test("toggleFilter adds, removes, and never mutates", () => {
  const base = emptyFilters();
  const on = toggleFilter(base, "language", "Go");
  const off = toggleFilter(on, "language", "Go");
  assert.deepEqual(base.language, []);
  assert.deepEqual(on.language, ["Go"]);
  assert.deepEqual(off.language, []);
});

test("multi-valued labels match any selected label", () => {
  const f = toggleFilter(emptyFilters(), "labels", "tui");
  assert.ok(matchesFacets(rec("a/b", { labels: ["cli", "tui"] }), f));
  assert.ok(!matchesFacets(rec("a/b", { labels: ["cli"] }), f));
});
