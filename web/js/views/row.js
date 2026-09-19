// One result row. `onFilter(facetKey, value)` lets tags act as filters.

import { el, formatCount, safeUrl } from "../dom.js";
import { VALUE_LABELS } from "../core/facets.js";

const MAX_TAGS = 6;

function filterTag(text, className, facetKey, value, onFilter) {
  return el("button", {
    type: "button",
    class: `tag ${className}`,
    title: `Filter by ${text}`,
    text,
    onclick: () => onFilter(facetKey, value),
  });
}

export function renderRow(record, top, { categoryNames, onFilter, onSimilar }) {
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
  if (record.topics.length === 0) {
    foot.push(el("span", { class: "tag tag--untagged", title: "This repo has no GitHub topics", text: "no topics" }));
  } else {
    foot.push(el("span", {
      class: "row__topics",
      title: record.topics.join(", "),
      text: record.topics.slice(0, MAX_TAGS).map((t) => `#${t}`).join(" "),
    }));
  }
  foot.push(el("span", { class: "row__sep", text: "·" }));
  foot.push(el("span", { title: "Date you starred it", text: `starred ${record.starred}` }));
  if (record.similar && record.similar.length) {
    foot.push(el("button", {
      type: "button", class: "tag tag--similar", title: "Show repos most like this one",
      text: "≈ similar", onclick: () => onSimilar(record.name),
    }));
  }

  return el("article", { class: "row", style: `top:${top}px` },
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
  );
}
