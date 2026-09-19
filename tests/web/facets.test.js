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

test("topic filter matches any selected GitHub topic", () => {
  const R = [rec("a/1", { topics: ["cli", "rust"] }), rec("b/2", { topics: ["web"] }), rec("c/3")];
  const f = toggleFilter(emptyFilters(), "topic", "rust");
  assert.deepEqual(R.filter((r) => matchesFacets(r, f)).map((r) => r.name), ["a/1"]);
});

test("topic facet is hidden from the sidebar but still counted", async () => {
  const { FACET_BY_KEY } = await import("../../web/js/core/facets.js");
  assert.equal(FACET_BY_KEY.topic.hidden, true);
  const counts = countFacets([rec("a/1", { topics: ["cli"] })], emptyFilters());
  assert.equal(counts.topic.get("cli"), 1);
});

test("topic filter also finds repos where the topic is only suggested", () => {
  const R = [rec("a/1", { topics: ["osint"] }), rec("b/2", { suggested_topics: ["osint"] }), rec("c/3")];
  const f = toggleFilter(emptyFilters(), "topic", "osint");
  assert.deepEqual(R.filter((r) => matchesFacets(r, f)).map((r) => r.name), ["a/1", "b/2"]);
});

test("has-topics facet still reflects real GitHub topics only", () => {
  const counts = countFacets([rec("b/2", { suggested_topics: ["osint"] })], emptyFilters());
  assert.equal(counts.topics_state.get("none"), 1);
});
