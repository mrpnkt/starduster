// Facet definitions and disjunctive counting. Pure: no DOM, no globals.
//
// Semantics: options inside one facet are OR-ed, facets are AND-ed together.
// A facet's counts ignore that facet's own selection ("disjunctive faceting"),
// so ticking "Go" never makes "Rust" drop to zero and become unclickable.

export const FACETS = Object.freeze([
  { key: "category", param: "cat", label: "Category", get: (r) => r.category ? [r.category] : ["__none"] },
  { key: "maintenance", param: "maint", label: "Maintenance", get: (r) => [r.maintenance] },
  { key: "language", param: "lang", label: "Language", get: (r) => [r.language || "__none"] },
  { key: "labels", param: "label", label: "Form factor", get: (r) => r.labels },
  { key: "starred_year", param: "year", label: "Starred in", get: (r) => [r.starred_year] },
  { key: "stars_bucket", param: "stars", label: "Popularity", get: (r) => [r.stars_bucket] },
  { key: "topics_state", param: "topics", label: "GitHub topics", get: (r) => [r.topics.length ? "has" : "none"] },
  // Thousands of distinct values, so not listed in the sidebar: applied by
  // clicking a topic on a repo, and shown as a removable chip.
  // Includes suggested topics, so clicking #osint also finds untagged OSINT repos.
  { key: "topic", param: "topic", label: "Topic", get: (r) => [...r.topics, ...(r.suggested_topics || [])], hidden: true },
]);

export const FACET_BY_KEY = Object.freeze(Object.fromEntries(FACETS.map((f) => [f.key, f])));

// Fixed display orders for facets whose values have a natural order.
export const VALUE_ORDER = Object.freeze({
  maintenance: ["active", "stale", "dormant", "archived", "unknown"],
  stars_bucket: ["50k+", "10k-50k", "1k-10k", "100-1k", "<100"],
  topics_state: ["none", "has"],
});

export const VALUE_LABELS = Object.freeze({
  maintenance: { active: "Active (< 6 months)", stale: "Stale (6–24 months)", dormant: "Dormant (> 2 years)", archived: "Archived", unknown: "Unknown" },
  topics_state: { none: "No topics", has: "Has topics" },
  __none: "(none)",
});

export function emptyFilters() {
  return Object.freeze(Object.fromEntries(FACETS.map((f) => [f.key, Object.freeze([])])));
}

/** True if `record` satisfies every facet except `skipKey`. */
export function matchesFacets(record, filters, skipKey = null) {
  for (const facet of FACETS) {
    if (facet.key === skipKey) continue;
    const selected = filters[facet.key];
    if (!selected || selected.length === 0) continue;
    const values = facet.get(record);
    if (!values.some((v) => selected.includes(v))) return false;
  }
  return true;
}

/**
 * Count option values per facet over `records` (already narrowed by search
 * and view). Returns `{ facetKey: Map(value -> count) }`.
 */
export function countFacets(records, filters) {
  const out = {};
  for (const facet of FACETS) {
    const counts = new Map();
    for (const record of records) {
      if (!matchesFacets(record, filters, facet.key)) continue;
      for (const value of facet.get(record)) {
        counts.set(value, (counts.get(value) || 0) + 1);
      }
    }
    out[facet.key] = counts;
  }
  return out;
}

/** Return a new filters object with `value` toggled in facet `key`. */
export function toggleFilter(filters, key, value) {
  const current = filters[key] || [];
  const next = current.includes(value)
    ? current.filter((v) => v !== value)
    : [...current, value];
  return Object.freeze({ ...filters, [key]: Object.freeze(next) });
}
