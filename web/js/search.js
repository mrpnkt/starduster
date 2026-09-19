// Full-text search over the catalog, backed by the vendored MiniSearch.

const FIELDS = ["name", "summary", "description", "labels", "topics", "categoryName"];

export function createSearch(records, categoryNames) {
  const MiniSearch = globalThis.MiniSearch;
  if (!MiniSearch) throw new Error("MiniSearch failed to load (web/vendor/minisearch.js)");

  const index = new MiniSearch({
    fields: FIELDS,
    idField: "name",
    extractField: (doc, field) => {
      if (field === "labels") return doc.labels.join(" ");
      if (field === "topics") return [...doc.topics, ...(doc.suggested_topics || [])].join(" ");
      if (field === "categoryName") return categoryNames.get(doc.category) || "";
      return doc[field] ?? "";
    },
    searchOptions: {
      prefix: true,
      fuzzy: 0.2,
      combineWith: "AND",
      boost: { name: 3, summary: 2, labels: 1.5, categoryName: 1.5 },
    },
  });
  index.addAll(records);

  /** Returns Map(name -> score), or null for an empty query. */
  return function search(query) {
    const q = query.trim();
    if (!q) return null;
    return new Map(index.search(q).map((hit) => [hit.id, hit.score]));
  };
}
