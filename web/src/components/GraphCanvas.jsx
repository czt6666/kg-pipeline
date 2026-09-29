import { memo, useEffect, useRef } from "react";
import * as echarts from "echarts";
import { colorForType, labelForType } from "../utils/types.js";

/* ---------- ECharts graph wrapper ----------
   Switched from Cytoscape's cose layout to ECharts' force layout because
   labelLayout.hideOverlap gives us automatic label-collision avoidance —
   with dozens of nodes, static label placement always turned into unreadable
   stacked text; ECharts hides/shifts labels that would overlap instead.

   No click-to-highlight-adjacency here on purpose: the emphasis/blur/focus
   machinery for that (bolding a node + its edges, dimming everything else)
   went through several rounds of visual bugs (edge labels detaching on zoom,
   highlighted edges not restyling their labels) and wasn't worth the upkeep.
   Clicking a node still calls onSelectNode so callers can sync a sidebar/text
   view. The one bit of visual feedback we do keep is `highlightId`: a plain
   dispatchAction('highlight'/'downplay') with a series-level emphasis.itemStyle —
   no `focus`, no `blur`, no labelLayout involved — so it can't regress into the
   same bugs.

   Force layout stays live (`layout:'force'`, `draggable:true`,
   `force.layoutAnimation:true`, the ECharts default) so dragging a node
   pushes its neighbors around like real physics, not a rigid single-node
   move — that reactive feel is the point, not a side effect. An earlier
   version froze the layout into static `layout:'none'` coordinates after the
   initial settle specifically to make dragging inert (no physics, so nothing
   could ever thrash) — that version was safer but gave up neighbor reaction
   entirely, which is the wrong trade for this app. Going back to a live
   simulation means the initial-settle animation is back too, so it's masked
   with a plain opacity hide/fade instead of trying to suppress it via
   `layoutAnimation:false` (toggling that flag between an initial silent pass
   and a later interactive pass doesn't work — ECharts' force stage handler
   rebuilds the whole simulation from full-strength friction on every
   setOption regardless of preserved positions, so flipping the flag just
   relocates the visible shake to right after the flip instead of removing
   it). `animation:false` is unrelated and stays on regardless: it kills
   ECharts' own view re-center/re-scale glide on data changes (a separate
   animation system from `force.layoutAnimation`), which is what caused a
   ~500-900ms whole-graph pan on recenter. */
export const GraphCanvas = memo(function GraphCanvas({ nodes, edges, centerId, onSelectNode, onSelectEdge, highlightId }) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  const nodeDataRef = useRef([]);
  const onSelectRef = useRef(onSelectNode);
  onSelectRef.current = onSelectNode;
  const onSelectEdgeRef = useRef(onSelectEdge);
  onSelectEdgeRef.current = onSelectEdge;

  useEffect(() => {
    if (!ref.current) return;
    const localDeg = {};
    for (const n of nodes) localDeg[n.entity_id] = 0;
    for (const e of edges) { localDeg[e.head] = (localDeg[e.head]||0)+1; localDeg[e.tail] = (localDeg[e.tail]||0)+1; }

    const nodeData = nodes.map(n => {
      const deg = localDeg[n.entity_id] || 0;
      const isCenter = n.entity_id === centerId;
      const color = colorForType(n.type);
      return {
        id: n.entity_id,
        name: n.name,
        value: deg,
        symbolSize: isCenter ? 42 : 12 + Math.min(24, deg * 3.2),
        itemStyle: {
          color,
          borderColor: isCenter ? "#161a2b" : "#ffffff",
          borderWidth: isCenter ? 3 : 1.5,
          shadowColor: "rgba(22,26,43,.18)", shadowBlur: 6,
        },
        label: { show: true, fontWeight: isCenter ? 700 : 500 },
        _type: n.type, _typeLabel: labelForType(n.type), _deg: deg,
      };
    });
    // Declutter: only label the edges that touch the ego center — otherwise every
    // edge's relation label overlaps into unreadable noise.
    const edgeData = edges.map(e => {
      const touches = !centerId || e.head === centerId || e.tail === centerId;
      // condition is a plain string as of v4_pro prompts; older extractions stored
      // {"raw": ...} -- normalize here so the tooltip/detail panel don't care which.
      const condition = typeof e.condition === "string" ? e.condition : e.condition?.raw || null;
      return {
        source: e.head, target: e.tail,
        value: e.relation,
        _condition: condition,
        label: { show: touches },
        lineStyle: touches
          ? { color: "#94a1b8", opacity: 0.9, width: 1.5 }
          : { color: "#dde1ea", opacity: 0.6, width: 1 },
      };
    });

    nodeDataRef.current = nodeData;
    const chart = chartRef.current || echarts.init(ref.current);
    chartRef.current = chart;

    // animation:false kills ECharts' own view re-center/re-scale glide on data
    // changes (see file header) — unrelated to force.layoutAnimation below, which
    // stays true so drag keeps its reactive push-neighbors-away feel.
    chart.setOption({
      animation: false,
      tooltip: {
        trigger: "item",
        backgroundColor: "rgba(22,26,43,.94)",
        borderWidth: 0,
        padding: [6, 10],
        textStyle: { color: "#f2f3f7", fontSize: 12 },
        formatter: p => p.dataType === "node"
          ? `<b>${p.data.name}</b> · ${p.data._typeLabel}<br/>${p.data._deg} 条关系`
          : p.data._condition
            ? `${p.data.value}<br/><span style="color:#b5bdd0">条件：${p.data._condition}</span>`
            : p.data.value,
      },
      series: [{
        type: "graph",
        layout: "force",
        roam: true,
        scaleLimit: { min: 0.3, max: 5 },
        draggable: true,
        cursor: "pointer",
        // initLayout:'circular' seeds nodes on a ring instead of at random so the
        // simulation has less distance to travel, shortening the settle-in this
        // component hides behind the opacity fade below.
        force: { repulsion: 190, edgeLength: [45, 170], gravity: 0.12, friction: 0.55, initLayout: "circular" },
        label: {
          show: true, position: "right", distance: 6, fontSize: 11,
          color: "#3a4157",
          textBorderColor: "#f6f7fb", textBorderWidth: 3,
        },
        // No labelLayout here on purpose: setting *any* labelLayout (even one that
        // only targets node labels) makes ECharts route every label — nodes AND
        // edges — through its label-layout manager, which repositions labels in
        // absolute screen space instead of the element's local (auto-transforming)
        // space. That space only gets recomputed on full re-layouts, not on plain
        // roam (wheel-zoom/drag-pan), so labels visibly stopped tracking their
        // node/edge during zoom/pan. Plain anchored labels track correctly; we
        // declutter edges by only labeling the ones touching the ego center below.
        edgeLabel: {
          show: true, fontSize: 9.5, color: "#8890a4",
          textBorderColor: "#f6f7fb", textBorderWidth: 3,
          formatter: p => p.data.value,
        },
        edgeSymbol: ["none", "arrow"],
        edgeSymbolSize: 6,
        lineStyle: { curveness: 0.04 },
        emphasis: {
          scale: 1.18,
          itemStyle: {
            borderColor: "#4f46e5", borderWidth: 2.5,
            shadowColor: "rgba(79,70,229,.5)", shadowBlur: 16,
          },
          label: { fontWeight: 700 },
        },
        data: nodeData,
        links: edgeData,
      }],
    }, true);

    // Mask the live settle-in behind an opacity fade instead of suppressing it:
    // hide the canvas immediately, then fade it in once the layout has had
    // enough time to visually stop moving. clearTimeout on cleanup so a fast
    // dataset switch / recenter doesn't fade in a stale, disposed chart.
    const el = ref.current;
    el.style.transition = "none";
    el.style.opacity = "0";
    const revealTimer = setTimeout(() => {
      el.style.transition = "opacity 240ms ease";
      el.style.opacity = "1";
    }, 450);

    chart.off("click");
    chart.on("click", params => {
      if (params.dataType === "node") onSelectRef.current(params.data.id);
      else if (params.dataType === "edge" && onSelectEdgeRef.current)
        onSelectEdgeRef.current({
          head: params.data.source, tail: params.data.target,
          relation: params.data.value, condition: params.data._condition,
        });
    });

    return () => { clearTimeout(revealTimer); chart.dispose(); chartRef.current = null; };
  }, [nodes, edges, centerId]);

  // Plain highlight/downplay dispatchAction — lightweight (update:'none'), doesn't
  // touch layout, and with no `focus`/`blur` set above it only affects this one
  // item, so it can't cause the freezing/detaching bugs the old adjacency-highlight
  // feature had.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.dispatchAction({ type: "downplay", seriesIndex: 0 });
    if (highlightId != null) {
      const idx = nodeDataRef.current.findIndex(n => n.id === highlightId);
      if (idx >= 0) chart.dispatchAction({ type: "highlight", seriesIndex: 0, dataIndex: idx });
    }
  }, [highlightId, nodes, edges, centerId]);

  // ECharts' own wheel-zoom (RoamController._mousewheelHandler) applies a *fixed*
  // per-event factor (1.1/1.2/1.4 depending on delta magnitude) with 1.1 as the
  // floor — shrinking the event's delta can only push it into a smaller bucket, it
  // can never go below that 1.1 floor. A single soft trackpad nudge fires many
  // wheel events, each still getting at least ×1.1, compounding into a big jump —
  // which is what read as "too sensitive". So instead of damping and handing the
  // event to ECharts' handler, we take over entirely: swallow the native event and
  // dispatch the graph's roam action ourselves with a continuous, much gentler
  // scale computed directly from this event's actual delta (no artificial floor).
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onWheel = e => {
      e.preventDefault();
      e.stopPropagation();
      const chart = chartRef.current;
      if (!chart) return;
      const dy = Math.max(-200, Math.min(200, e.deltaY));
      const scale = Math.exp(-dy * 0.0005);
      chart.dispatchAction({ type: "graphRoam", zoom: scale, originX: e.offsetX, originY: e.offsetY });
    };
    el.addEventListener("wheel", onWheel, { capture: true, passive: false });

    const ro = new ResizeObserver(() => { if (chartRef.current) chartRef.current.resize(); });
    ro.observe(el);

    return () => { el.removeEventListener("wheel", onWheel, { capture: true }); ro.disconnect(); };
  }, []);

  return <div className="canvas-inner" ref={ref} />;
});
