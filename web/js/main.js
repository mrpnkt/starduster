// Entry point: load data, own the state, re-render on change.

import { el } from "./dom.js";
import { countFacets, emptyFilters, FACET_BY_KEY, toggleFilter } from "./core/facets.js";
import { selectResults } from "./core/filters.js";
import { parseState, serializeState, withState } from "./core/url-state.js";
import { createSearch } from "./search.js";
import { renderRow } from "./views/row.js";
import { createSidebar } from "./views/sidebar.js";
import { createVirtualList } from "./views/virtual-list.js";

const DATA_URL = "data/repos.json";
const SEARCH_DEBOUNCE_MS = 120;
const THEME_KEY = "starduster-theme";

const $ = (id) => document.getElementById(id);

async function loadCatalog() {
  const response = await fetch(DATA_URL, { cache: "no-cache" });
  if (!response.ok) throw new Error(`Could not load ${DATA_URL} (HTTP ${response.status})`);
  const payload = await response.json();
  if (!payload || !Array.isArray(payload.repos) || !payload.taxonomy) {
    throw new Error(`${DATA_URL} is malformed`);
  }
  return payload;
}

function applyTheme(theme) {
  if (theme === "dark" || theme === "light") document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}

function initTheme() {
  let stored = null;
  try { stored = localStorage.getItem(THEME_KEY); } catch { /* storage blocked */ }
  applyTheme(stored);
  $("theme-toggle").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme === "dark" ||
      (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
    const next = dark ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem(THEME_KEY, next); } catch { /* storage blocked */ }
  });
}

function renderMeta(meta) {
  const date = (meta.generated_at || "").slice(0, 10);
  $("corpus-meta").textContent =
    `${meta.total.toLocaleString()} starred · ${meta.untagged.toLocaleString()} with no GitHub topics` +
    (meta.unclassified ? ` · ${meta.unclassified.toLocaleString()} unsorted` : "") +
    (date ? ` · updated ${date}` : "");
}

function start(payload) {
  const { repos, taxonomy, meta } = payload;
  const categoryNames = new Map(taxonomy.categories.map((c) => [c.id, c.name]));
  const search = createSearch(repos, categoryNames);

  let state = parseState(location.search);
  let scores = search(state.q);

  const sidebar = createSidebar({ container: $("facet-groups"), taxonomy, categoryNames, onToggle });
  const list = createVirtualList({
    viewport: $("viewport"), spacer: $("spacer"), rows: $("rows"),
    renderItem: (record, top) => renderRow(record, top, {
      categoryNames, onFilter: onToggle,
      onSimilar: (name) => setState(withState(state, { like: name })),
    }),
  });

  function setState(next, { resetScroll = true } = {}) {
    state = next;
    history.replaceState(null, "", serializeState(state) || location.pathname);
    render({ resetScroll });
  }

  function onToggle(key, value) {
    setState(withState(state, { filters: toggleFilter(state.filters, key, value) }));
  }

  function renderChips() {
    const chips = [];
    if (state.like) {
      chips.push(el("span", { class: "chip" }, `Similar to ${state.like}`,
        el("button", { type: "button", "aria-label": "Leave similar view", text: "×",
          onclick: () => setState(withState(state, { like: "" })) })));
    }
    for (const [key, values] of Object.entries(state.filters)) {
      for (const value of values) {
        chips.push(el("span", { class: "chip" },
          `${FACET_BY_KEY[key].label}: ${sidebar.labelFor(key, value)}`,
          el("button", { type: "button", "aria-label": "Remove filter", text: "×", onclick: () => onToggle(key, value) }),
        ));
      }
    }
    $("active-filters").replaceChildren(...chips);
  }

  function render({ resetScroll = true } = {}) {
    const { base, results } = selectResults(repos, state, scores);
    sidebar.render(state, countFacets(base, state.filters));
    list.setItems(results, { resetScroll });
    renderChips();

    $("result-count").replaceChildren(
      el("strong", { text: results.length.toLocaleString() }),
      ` of ${repos.length.toLocaleString()} repos`,
    );
    $("empty-state").hidden = results.length > 0;
    $("clear-search").hidden = !state.q;
    $("search").value = state.q;
    $("sort").value = state.sort;
    for (const btn of document.querySelectorAll(".view-btn")) {
      btn.classList.toggle("is-active", !state.like && btn.dataset.view === state.view);
    }
  }

  let debounce = 0;
  $("search").addEventListener("input", (event) => {
    clearTimeout(debounce);
    const q = event.target.value;
    debounce = setTimeout(() => {
      scores = search(q);
      setState(withState(state, { q, like: "" }));
    }, SEARCH_DEBOUNCE_MS);
  });
  $("clear-search").addEventListener("click", () => {
    scores = null;
    setState(withState(state, { q: "" }));
    $("search").focus();
  });
  $("sort").addEventListener("change", (e) => setState(withState(state, { sort: e.target.value })));
  $("toggle-filters").addEventListener("click", (e) => {
    const open = $("facets").classList.toggle("is-open");
    e.currentTarget.setAttribute("aria-expanded", String(open));
    e.currentTarget.textContent = open ? "Hide" : "Show";
  });
  $("reset-filters").addEventListener("click", () => setState(withState(state, { filters: emptyFilters() })));

  for (const btn of document.querySelectorAll(".view-btn")) {
    btn.addEventListener("click", () => {
      const view = btn.dataset.view;
      // Clicking Rediscover again draws a fresh handful.
      const seed = view === "rediscover" ? Math.floor(Math.random() * 1e9) + 1 : state.seed;
      setState(withState(state, { view, seed, like: "" }));
    });
  }

  renderMeta(meta);
  render();
}

initTheme();
loadCatalog()
  .then(start)
  .catch((error) => {
    console.error(error);
    $("corpus-meta").textContent = "Could not load the catalog.";
    const empty = $("empty-state");
    empty.textContent = `${error.message}. Run \`starduster build\` to generate it.`;
    empty.hidden = false;
  });

