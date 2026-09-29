import { useEffect, useMemo, useState } from "react";
import { TopBar } from "../components/TopBar.jsx";
import { GraphCanvas } from "../components/GraphCanvas.jsx";
import { ResizeHandle } from "../components/ResizeHandle.jsx";
import { useResizer } from "../hooks/useResizer.js";
import { getJSON } from "../utils/api.js";
import { colorForType, labelForType } from "../utils/types.js";
import { mergeKey, mergeLabel } from "../utils/merged.js";

/* 检索：面向 agent 的精确名词查询——关键词/语义/图 Pattern 三路召回 + 融合排序，命中的
   候选实体消歧后，中间展示子图（profile 一跳扇出 + 命中的多跳 pattern 拼成的可视化图），
   右侧展示子图对应的可读解释文本 + 结构化事实列表（src/retrieval/pipeline.py）。 */
export function Retrieval() {
  const [mergedList, setMergedList] = useState([]);
  const [selectedKey, setSelectedKey] = useState(null);
  const [term, setTerm] = useState("");
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [activeExpanded, setActiveExpanded] = useState(null);
  const [expandLoading, setExpandLoading] = useState(false);
  // Separate from activeId (= the resolved "seed" a fetched subgraph/explanation is
  // centered on): clicking a node *inside* the canvas only highlights it, mirroring
  // GraphExplorer's inspectNode/selectFocus split -- see inspectNode below.
  const [highlightId, setHighlightId] = useState(null);
  // Recenter history: every explicit "设为中心" push the *previous* center here, so
  // "← 返回" can pop back through a chain of jumps (e.g. 感冒 -> 风寒束表证 -> 辛温解表
  // -> back -> back) instead of only ever undoing one step.
  const [focusStack, setFocusStack] = useState([]);
  // entity_id currently awaiting its async LLM summary (see fetchSummary) -- distinct
  // from expandLoading, which only covers the fast facts/subgraph fetch.
  const [summaryPendingId, setSummaryPendingId] = useState(null);
  const [leftW, leftDrag] = useResizer(280, { min: 220, max: 480 });
  const [rightW, rightDrag] = useResizer(380, { min: 280, max: 600, invert: true });

  useEffect(() => {
    getJSON("/api/merged").then(list => {
      setMergedList(list);
      if (list.length) setSelectedKey(mergeKey(list[0]));
    });
  }, []);

  const selected = useMemo(() => mergedList.find(m => mergeKey(m) === selectedKey) || null, [mergedList, selectedKey]);
  const dataset = selected?.dataset ?? null;
  const merge = selected?.merge || "merged";

  // The one LLM call in this flow (a few seconds) -- split into its own request so the
  // facts/subgraph render immediately instead of the whole panel blocking on it (see
  // src/retrieval/pipeline.py's module docstring on why expand_entity itself never calls
  // the LLM anymore). Guards against a stale response landing after the user has already
  // navigated elsewhere by checking the entity_id still matches when it resolves.
  const fetchSummary = (entityId) => {
    setSummaryPendingId(entityId);
    getJSON(`/api/retrieval/summary?dataset=${dataset}&merge=${merge}&entity_id=${encodeURIComponent(entityId)}&top_k=10`)
      .then(r => {
        setActiveExpanded(prev => (prev && prev.seed.entity_id === entityId) ? { ...prev, summary: r.summary } : prev);
      })
      .catch(() => {})
      .finally(() => setSummaryPendingId(prev => (prev === entityId ? null : prev)));
  };

  const runSearch = () => {
    if (!term.trim() || !dataset) return;
    setSearching(true);
    setResult(null); setActiveId(null); setActiveExpanded(null); setFocusStack([]); setSummaryPendingId(null);
    getJSON(`/api/retrieval/search?dataset=${dataset}&merge=${merge}&term=${encodeURIComponent(term.trim())}&top_k=10`)
      .then(r => {
        setResult(r);
        setSearching(false);
        if (r.resolved) {
          setActiveId(r.resolved.seed.entity_id);
          setActiveExpanded(r.resolved);
          setHighlightId(r.resolved.seed.entity_id);
          fetchSummary(r.resolved.seed.entity_id);
        }
      })
      .catch(() => setSearching(false));
  };

  // Raw recenter (fetch + apply), with no stack bookkeeping -- shared by selectCandidate
  // (pushes first) and goBack (pops instead of pushing) so the fetch logic lives once.
  const goToEntity = (entityId) => {
    setHighlightId(entityId);
    setActiveId(entityId);
    if (result?.resolved?.seed.entity_id === entityId) {
      setActiveExpanded(result.resolved);
      fetchSummary(entityId);
      return;
    }
    setExpandLoading(true);
    getJSON(`/api/retrieval/expand?dataset=${dataset}&merge=${merge}&entity_id=${encodeURIComponent(entityId)}&top_k=10`)
      .then(r => { setActiveExpanded(r); setExpandLoading(false); fetchSummary(entityId); })
      .catch(() => setExpandLoading(false));
  };

  // Explicit recenter: refetches the subgraph/explanation around entityId -- used by the
  // candidate list (an intentional "look at this one instead") and by the canvas's
  // "设为中心" action, never by a plain click inside the canvas (see inspectNode).
  const selectCandidate = (entityId) => {
    if (entityId === activeId) { setHighlightId(entityId); return; }
    if (activeId) setFocusStack(prev => [...prev, activeId]);
    goToEntity(entityId);
  };

  const goBack = () => {
    setFocusStack(prev => {
      if (!prev.length) return prev;
      goToEntity(prev[prev.length - 1]);
      return prev.slice(0, -1);
    });
  };

  // Inspect: highlights a node clicked directly in the canvas without recentering the
  // view or refetching anything -- matches GraphExplorer's inspectNode (the view should
  // never jump just because you clicked something in it).
  const inspectNode = (entityId) => setHighlightId(entityId);

  const highlightNode = useMemo(() => {
    if (!highlightId || !activeExpanded) return null;
    return activeExpanded.subgraph.nodes.find(n => n.entity_id === highlightId) || null;
  }, [highlightId, activeExpanded]);

  return (
    <>
      <TopBar route="retrieval" />
      <div className="explorer">
        <div className="explorer-top">
          <select className="dataset-select" value={selectedKey || ""} onChange={e => setSelectedKey(e.target.value)}>
            {mergedList.map(m => <option key={mergeKey(m)} value={mergeKey(m)}>{mergeLabel(m)}</option>)}
          </select>
          <div className="search-box">
            <input value={term} onChange={e => setTerm(e.target.value)} placeholder="输入专业中医名词，如 石淋证 / 麻黄汤 / 阳虚"
                   onKeyDown={e => e.key === "Enter" && runSearch()} disabled={searching} style={{ width:280 }} />
            <button className="primary" onClick={runSearch} disabled={searching}>{searching ? "检索中…" : "检索"}</button>
          </div>
          <span className="hint">输入契约：给一个明确的专业名词（不是整句问题），三路召回 + 融合排序后展示最可能的实体画像。</span>
        </div>

        <div className="explorer-body" style={{ gridTemplateColumns: `${leftW}px 6px 1fr 6px ${rightW}px` }}>
          <aside className="rail" style={{ background: "var(--surface-1)" }}>
            <h3>候选实体</h3>
            {searching ? (
              <div className="loading-row"><span className="spinner" />检索中…</div>
            ) : !result ? (
              <div className="hint">输入名词后点击"检索"。</div>
            ) : result.candidates.length === 0 ? (
              <div className="hint">未命中任何候选实体。</div>
            ) : (
              <div className="res-box">
                {result.candidates.map(c => (
                  <div key={c.entity_id}
                       className={"res-item clickable" + (c.entity_id === activeId ? " active" : "")}
                       onClick={() => selectCandidate(c.entity_id)}>
                    <span>
                      <b style={{ color: colorForType(c.type) }}>{c.name}</b>
                      <span className="muted"> （{labelForType(c.type)}）</span>
                    </span>
                    <span className="score">{c.fused_score.toFixed(3)}</span>
                  </div>
                ))}
              </div>
            )}
          </aside>

          <ResizeHandle onMouseDown={leftDrag} />

          <section className="canvas-col">
            <div className="canvas-toolbar">
              {focusStack.length > 0 && (
                <button className="link" onClick={goBack} style={{ marginRight: 10 }}>← 返回</button>
              )}
              {activeExpanded
                ? <span className="focus-label">子图 <b style={{ color: colorForType(activeExpanded.seed.type) }}>{activeExpanded.seed.name}</b>
                    <span className="muted"> （{labelForType(activeExpanded.seed.type)}）</span></span>
                : <span className="muted">检索后在此查看子图</span>}
              {activeExpanded && (
                <span className="muted" style={{ marginLeft: 10 }}>
                  {activeExpanded.subgraph.nodes.length} 节点 / {activeExpanded.subgraph.edges.length} 条关系
                </span>
              )}
              {activeExpanded && highlightNode && highlightId !== activeExpanded.seed.entity_id && (
                <span className="focus-label" style={{ marginLeft: 10 }}>· 已选中 <b style={{ color: colorForType(highlightNode.type) }}>{highlightNode.name}</b>
                  <button className="link" style={{ marginLeft: 8 }} onClick={() => selectCandidate(highlightId)}>设为中心 →</button>
                </span>
              )}
            </div>
            <div className="canvas">
              {expandLoading ? <div className="empty">加载子图中…</div>
                : !activeExpanded ? <div className="empty">左侧选择一个候选实体查看子图</div>
                : activeExpanded.subgraph.nodes.length === 0 ? <div className="empty">该实体没有可展开的关系</div>
                : <GraphCanvas nodes={activeExpanded.subgraph.nodes} edges={activeExpanded.subgraph.edges}
                               onSelectNode={inspectNode} centerId={activeExpanded.seed.entity_id} highlightId={highlightId} />}
            </div>
            <div className="hint" style={{ padding: "6px 16px" }}>子图 = profile 一跳扇出 + 命中的多跳 pattern（右侧解释文本的图形化版本）。点击子图里节点仅高亮查看，不会跳转；需要以它为中心重新展开时点"设为中心"。</div>
          </section>

          <ResizeHandle onMouseDown={rightDrag} />

          <aside className="rail right" style={{ overflow: "auto" }}>
            {!activeExpanded ? (
              <div className="hint">左侧选择一个候选实体，查看它子图对应的可读解释。</div>
            ) : (
              <div className="detail">
                <div className="detail-head">
                  <span style={{ color: colorForType(activeExpanded.seed.type) }}>{activeExpanded.seed.name}</span>
                  <span className="type-badge" style={{ color: colorForType(activeExpanded.seed.type) }}>
                    {labelForType(activeExpanded.seed.type)}
                  </span>
                </div>

                <h3>结构化事实（{activeExpanded.facts.length}）</h3>
                <div className="res-box">
                  {activeExpanded.facts.map((f, i) => (
                    <div className="res-item" key={i}>
                      <span>{f.sentence}</span>
                      <span className="score">{f.source}</span>
                    </div>
                  ))}
                </div>

                <h3 style={{ marginTop: 16 }}>
                  LLM 总结
                  {summaryPendingId === activeExpanded.seed.entity_id ? "（生成中…）"
                    : !activeExpanded.summary ? "（生成失败，回退为模板文本）" : ""}
                </h3>
                <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.9, fontSize: 13, margin: "12px 0 4px", color: "var(--ink-2)" }}>
                  {summaryPendingId === activeExpanded.seed.entity_id && !activeExpanded.summary
                    ? <span className="loading-row"><span className="spinner" />异步生成中，可先看上方结构化事实…</span>
                    : (activeExpanded.summary || activeExpanded.text)}
                </div>
              </div>
            )}
          </aside>
        </div>
      </div>
    </>
  );
}
