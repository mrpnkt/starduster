// Filter sidebar. Re-rendered from state + counts; holds only UI-local state
// (which facets are collapsed or expanded).

import { el } from "../dom.js";
import { FACETS, VALUE_LABELS, VALUE_ORDER } from "../core/facets.js";

const COLLAPSED_LIMIT = 8;
const DEFAULT_COLLAPSED = new Set(["stars_bucket", "starred_year", "topics_state"]);

export function createSidebar({ container, taxonomy, categoryNames, onToggle }) {
  const collapsed = new Set(DEFAULT_COLLAPSED);
  const expanded = new Set();

  function labelFor(key, value) {
    if (value === "__none") return key === "category" ? "Unsorted" : VALUE_LABELS.__none;
    if (key === "category") return categoryNames.get(value) || value;
    return VALUE_LABELS[key]?.[value] || value;
  }

  function orderedValues(key, counts, selected) {
    const values = new Set([...counts.keys(), ...selected]);
    if (VALUE_ORDER[key]) return VALUE_ORDER[key].filter((v) => values.has(v));
    if (key === "starred_year") return [...values].sort().reverse();
    return [...values].sort((a, b) => (counts.get(b) || 0) - (counts.get(a) || 0) || a.localeCompare(b));
  }

  function option(key, value, count, isSelected) {
    return el("label", { class: `opt${count ? "" : " is-empty"}` },
      el("input", {
        type: "checkbox",
        checked: isSelected,
        onchange: () => onToggle(key, value),
      }),
      el("span", { class: "opt__label", title: labelFor(key, value), text: labelFor(key, value) }),
      el("span", { class: "opt__count", text: count || 0 }),
    );
  }

  function categoryBody(counts, selected) {
    const blocks = [];
    for (const group of taxonomy.groups) {
      const children = taxonomy.categories.filter((c) => c.parent === group.id);
      const visible = children.filter((c) => counts.get(c.id) || selected.includes(c.id));
      if (!visible.length) continue;
      blocks.push(el("div", { class: "facet__group-label", text: group.name }));
      for (const c of visible) blocks.push(option("category", c.id, counts.get(c.id), selected.includes(c.id)));
    }
    if (counts.get("__none") || selected.includes("__none")) {
      blocks.push(el("div", { class: "facet__group-label", text: "No close category" }));
      blocks.push(option("category", "__none", counts.get("__none"), selected.includes("__none")));
    }
    return blocks;
  }

  function listBody(key, counts, selected) {
    const values = orderedValues(key, counts, selected);
    const showAll = expanded.has(key) || values.length <= COLLAPSED_LIMIT + 2;
    const shown = showAll ? values : values.slice(0, COLLAPSED_LIMIT);
    const nodes = shown.map((v) => option(key, v, counts.get(v), selected.includes(v)));
    if (!showAll) {
      nodes.push(el("button", {
        type: "button", class: "facet__more",
        text: `Show all ${values.length}`,
        onclick: () => { expanded.add(key); render(lastState, lastCounts); },
      }));
    }
    return nodes;
  }

  let lastState = null;
  let lastCounts = null;

  function render(state, counts) {
    lastState = state;
    lastCounts = counts;
    const sections = FACETS.filter((facet) => !facet.hidden).map((facet) => {
      const selected = state.filters[facet.key] || [];
      const facetCounts = counts[facet.key];
      if (!facetCounts.size && !selected.length) return null;
      const isCollapsed = collapsed.has(facet.key) && !selected.length;
      const body = facet.key === "category"
        ? categoryBody(facetCounts, selected)
        : listBody(facet.key, facetCounts, selected);
      return el("section", { class: `facet${isCollapsed ? " is-collapsed" : ""}` },
        el("button", {
          type: "button", class: "facet__toggle",
          "aria-expanded": String(!isCollapsed),
          onclick: () => {
            if (collapsed.has(facet.key)) collapsed.delete(facet.key); else collapsed.add(facet.key);
            render(lastState, lastCounts);
          },
        }, facet.label, el("span", { class: "facet__chevron", text: "▾" })),
        el("div", { class: "facet__body" }, body),
      );
    });
    container.replaceChildren(...sections.filter(Boolean));
  }

  return { render, labelFor };
}
