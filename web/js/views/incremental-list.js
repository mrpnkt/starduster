// Renders results in pages of PAGE_SIZE and appends more as the end of the
// list scrolls into view. Rows keep their natural height, so a repo with many
// topics simply wraps onto more lines.

const PAGE_SIZE = 80;

export function createIncrementalList({ viewport, rows, renderItem }) {
  let items = [];
  let rendered = 0;
  const sentinel = document.createElement("div");
  sentinel.className = "list-sentinel";
  sentinel.setAttribute("aria-hidden", "true");

  function appendPage() {
    const end = Math.min(items.length, rendered + PAGE_SIZE);
    const fragment = document.createDocumentFragment();
    for (let i = rendered; i < end; i++) fragment.append(renderItem(items[i]));
    rendered = end;
    sentinel.before(fragment);
    sentinel.hidden = rendered >= items.length;
  }

  const observer = new IntersectionObserver(
    (entries) => { if (entries.some((e) => e.isIntersecting) && rendered < items.length) appendPage(); },
    { root: viewport, rootMargin: "600px 0px" },
  );

  return {
    setItems(next, { resetScroll = true } = {}) {
      items = next;
      rendered = 0;
      rows.replaceChildren(sentinel);
      if (resetScroll) viewport.scrollTop = 0;
      appendPage();
      observer.observe(sentinel);
    },
  };
}
