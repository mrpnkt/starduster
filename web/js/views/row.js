// One result row. `onFilter(facetKey, value)` lets tags act as filters.

import { el, formatCount, safeUrl } from "../dom.js";
import { VALUE_LABELS } from "../core/facets.js";

function filterTag(text, className, facetKey, value, onFilter) {
  return el("button", {
    type: "button",
    class: `tag ${className}`,
    title: `Filter by ${text}`,
    text,
    onclick: () => onFilter(facetKey, value),
  });
}

export function renderRow(record, { categoryNames, onFilter, onSimilar }) {
  const [owner, name] = record.name.split("/");
  const summaryText = record.summary || record.description;

  const foot = [];
  if (record.category) {
    foot.push(filterTag(categoryNames.get(record.category) || record.category,
      "tag--cat", "category", record.category, onFilter));
  }
  if (record.maintenance !== "active") {
    foot.push(el("span", {
      class: `pill pill--${record.maintenance}`,
      text: VALUE_LABELS.maintenance[record.maintenance] || record.maintenance,
    }));
  }
  foot.push(el("span", { class: "row__stars", title: `${record.stars} stars`, text: `★ ${formatCount(record.stars)}` }));
  if (record.language) {
    foot.push(filterTag(record.language, "", "language", record.language, onFilter));
  }
  for (const label of record.labels.slice(0, 3)) {
    foot.push(filterTag(label, "", "labels", label, onFilter));
  }
  foot.push(el("span", { class: "row__sep", text: "·" }));
  foot.push(el("span", { class: "row__date", title: "Last commit pushed to the repo", text: `updated ${record.pushed || "unknown"}` }));
  foot.push(el("span", { class: "row__date", title: "Date you starred it", text: `starred ${record.starred}` }));
  if (record.similar && record.similar.length) {
    foot.push(el("button", {
      type: "button", class: "tag tag--similar", title: "Show repos most like this one",
      text: "≈ similar", onclick: () => onSimilar(record.name),
    }));
  }

  return el("article", { class: "row" },
    el("div", { class: "row__head" },
      el("a", {
        class: "row__name",
        href: safeUrl(`https://github.com/${record.name}`),
        target: "_blank",
        rel: "noopener noreferrer",
      }, el("span", { class: "row__owner", text: `${owner}/` }), name),
    ),
    el("p", {
      class: `row__summary${record.summary ? "" : " row__summary--fallback"}`,
      title: record.summary && record.description ? record.description : null,
      text: summaryText || "No description.",
    }),
    el("div", { class: "row__foot" }, foot),
    el("div", { class: "row__topics" },
      record.topics.length
        ? record.topics.map((t) => filterTag(`#${t}`, "tag--topic", "topic", t, onFilter))
        : [
          el("span", { class: "tag tag--untagged", title: "This repo has no GitHub topics", text: "no topics" }),
          ...(record.suggested_topics || []).map((t) => el("button", {
            type: "button", class: "tag tag--suggested",
            title: `Suggested: ${t} is a topic shared by several similar repos. Click to filter.`,
            text: `≈#${t}`, onclick: () => onFilter("topic", t),
          })),
        ]),
  );
}
