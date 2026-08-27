import { useState } from "react";

// Drag-to-resize for adjacent panels. `invert` is for panels whose handle sits on
// their *left* edge, where dragging right should shrink them (not grow).
export function useResizer(initial, { min = 160, max = 640, invert = false } = {}) {
  const [size, setSize] = useState(initial);
  const onMouseDown = e => {
    e.preventDefault();
    const startX = e.clientX;
    const startSize = size;
    const onMove = ev => {
      const delta = ev.clientX - startX;
      setSize(Math.max(min, Math.min(max, startSize + (invert ? -delta : delta))));
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove, true);
      window.removeEventListener("mouseup", onUp, true);
      document.body.style.cursor = ""; document.body.style.userSelect = "";
    };
    // Capture phase, not bubble: the graph canvas (ECharts/zrender) has its own
    // mouse handlers for pan/drag and calls stopPropagation on them, which would
    // otherwise stop these events from ever reaching a bubble-phase window
    // listener once the cursor drags over the canvas — the resize would silently
    // stop tracking the mouse right as it crossed into the graph panel.
    window.addEventListener("mousemove", onMove, true);
    window.addEventListener("mouseup", onUp, true);
    document.body.style.cursor = "col-resize"; document.body.style.userSelect = "none";
  };
  return [size, onMouseDown];
}
