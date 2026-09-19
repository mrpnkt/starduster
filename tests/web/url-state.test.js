import { test } from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_STATE, parseState, serializeState, withState } from "../../web/js/core/url-state.js";
import { emptyFilters, toggleFilter } from "../../web/js/core/facets.js";

test("empty URL yields defaults", () => {
  assert.deepEqual(parseState(""), DEFAULT_STATE);
});

test("default state serializes to an empty string", () => {
  assert.equal(serializeState(DEFAULT_STATE), "");
});

test("round-trips query, view, sort and filters", () => {
  let filters = toggleFilter(emptyFilters(), "language", "C++");
  filters = toggleFilter(filters, "language", "C#");
  filters = toggleFilter(filters, "category", "cli-tools");
  const state = withState(DEFAULT_STATE, { q: "rate limit", view: "graveyard", sort: "stars_desc", filters });
  assert.deepEqual(parseState(serializeState(state)), state);
});

test("rediscover keeps its seed in the URL", () => {
  const state = withState(DEFAULT_STATE, { view: "rediscover", seed: 1234 });
  assert.match(serializeState(state), /seed=1234/);
  assert.equal(parseState(serializeState(state)).seed, 1234);
});

test("invalid view, sort and seed fall back to defaults", () => {
  const s = parseState("?view=evil&sort=<script>&seed=-5");
  assert.equal(s.view, "all");
  assert.equal(s.sort, "relevance");
  assert.equal(s.seed, 1);
});

test("duplicate filter params are collapsed and empties dropped", () => {
  assert.deepEqual(parseState("?lang=Go&lang=Go&lang=").filters.language, ["Go"]);
});

test("overlong query is truncated", () => {
  assert.equal(parseState(`?q=${"a".repeat(500)}`).q.length, 200);
});

test("like round-trips and rejects malformed names", () => {
  const state = withState(DEFAULT_STATE, { like: "owner/repo.name" });
  assert.equal(parseState(serializeState(state)).like, "owner/repo.name");
  assert.equal(parseState("?like=<script>").like, "");
  assert.equal(parseState("?like=noslash").like, "");
});

test("topic filters round-trip through the URL", () => {
  const filters = toggleFilter(emptyFilters(), "topic", "reverse-engineering");
  const state = withState(DEFAULT_STATE, { filters });
  assert.match(serializeState(state), /topic=reverse-engineering/);
  assert.deepEqual(parseState(serializeState(state)).filters.topic, ["reverse-engineering"]);
});
