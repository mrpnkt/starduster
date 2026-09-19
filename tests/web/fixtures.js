export function rec(name, over = {}) {
  return {
    name, description: "", summary: "", labels: [], topics: [],
    category: "cli-tools", secondary: [], confidence: 0.9,
    language: "Python", stars: 10, stars_bucket: "<100",
    maintenance: "active", pushed: "2026-01-01", starred: "2025-01-01",
    starred_year: "2025",
    ...over,
  };
}
