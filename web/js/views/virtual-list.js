// Windowed rendering: only rows intersecting the viewport (plus overscan) are
// in the DOM, so 3,267 results render as cheaply as 20.

const OVERSCAN = 6;

export function createVirtualList({ viewport, spacer, rows, renderItem }) {
  let items = [];
  let rowHeight = readRowHeight();
  let frame = 0;

  function readRowHeight() {
    const raw = getComputedStyle(document.documentElement).getPropertyValue("--row-height");
    return Number.parseFloat(raw) || 106;
  }

  function draw() {
    frame = 0;
    const { scrollTop, clientHeight } = viewport;
    const first = Math.max(0, Math.floor(scrollTop / rowHeight) - OVERSCAN);
    const last = Math.min(items.length, Math.ceil((scrollTop + clientHeight) / rowHeight) + OVERSCAN);
    const nodes = [];
    for (let i = first; i < last; i++) nodes.push(renderItem(items[i], i * rowHeight));
    rows.replaceChildren(...nodes);
  }

  function schedule() {
    if (!frame) frame = requestAnimationFrame(draw);
  }

  viewport.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", () => {
    rowHeight = readRowHeight();
    spacer.style.height = `${items.length * rowHeight}px`;
    schedule();
  });

  return {
    setItems(next, { resetScroll = true } = {}) {
      items = next;
      spacer.style.height = `${items.length * rowHeight}px`;
      if (resetScroll) viewport.scrollTop = 0;
      draw();
    },
  };
}
