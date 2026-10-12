import { useCallback, useEffect, useMemo, useState } from "react";
import { TopBar } from "../components/TopBar.jsx";
import { StatTile } from "../components/StatTile.jsx";
import { TypeBarChart } from "../components/TypeBarChart.jsx";
import { GraphCanvas } from "../components/GraphCanvas.jsx";
import { ResizeHandle } from "../components/ResizeHandle.jsx";
import { DocExtractionView } from "../components/DocExtractionView.jsx";
import { useResizer } from "../hooks/useResizer.js";
import { getJSON } from "../utils/api.js";
import { colorForType, labelForType } from "../utils/types.js";
import { buildAdjacency, egoSubgraph } from "../utils/graph.js";
import { mergeKey, mergeLabel } from "../utils/merged.js";

/* ---------- 完整知识图谱 ---------- */
export function GraphExplorer() {
  const [mergedList, setMergedList] = useState([]);
  // a dataset can hold several independently-merged graphs (see utils/merged.js) --
  // selectedKey is `${dataset}::${merge}` so distinct graphs of the same dataset
  // (e.g. TCM's merged_neike/merged_jichu/merged_zhenduan) are distinguishable
  const [selectedKey, setSelectedKey] = useState(null);
  const [graph, setGraph] = useState({ stats:{}, nodes:[], edges:[] });
  const [loading, setLoading] = useState(true);
  const [focusId, setFocusId] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [hops, setHops] = useState(2);
  const [budget, setBudget] = useState(80);
  const [docView, setDocView] = useState(null);
  const [docMatch, setDocMatch] = useState([]);
  const [docLoading, setDocLoading] = useState(false);
  const [typeFacet, setTypeFacet] = useState("ALL");
  const [leftW, leftDrag] = useResizer(280, { min: 220, max: 480 });
  const [rightW, rightDrag] = useResizer(340, { min: 260, max: 560, invert: true });
  const [searchTerm, setSearchTerm] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState(null);
  // Recenter history: selectFocus pushes the *previous* focus here before jumping, so
  // "← 返回" can walk back through a whole chain of jumps, not just undo the last one.
  const [focusStack, setFocusStack] = useState([]);

  useEffect(() => {
    getJSON("/api/kg/merged").then(list => {
      setMergedList(list);
      if (list.length) setSelectedKey(mergeKey(list[0]));
    });
  }, []);

  const selected = useMemo(() => mergedList.find(m => mergeKey(m) === selectedKey) || null, [mergedList, selectedKey]);
  const dataset = selected?.dataset ?? null;
  const merge = selected?.merge || "merged";
  const basePath = dataset ? `/api/kg/merged/${dataset}/${merge}` : null;

  useEffect(() => {
    if (!basePath) return;
    setLoading(true); setFocusId(null); setSelectedId(null); setDetail(null); setSelectedEdge(null); setTypeFacet("ALL"); setDocView(null);
    setSearchResults(null); setSearchTerm(""); setFocusStack([]);
    getJSON(basePath).then(g => {
      setGraph(g);
      setLoading(false);
      const deg = {};
      for (const e of g.edges) { deg[e.head] = (deg[e.head]||0)+1; deg[e.tail] = (deg[e.tail]||0)+1; }
      let top = null, topDeg = -1;
      for (const n of g.nodes) { const d = deg[n.entity_id]||0; if (d > topDeg) { topDeg = d; top = n.entity_id; } }
      if (top) { setFocusId(top); setSelectedId(top); }
    });
  }, [basePath]);

  const nodesById = useMemo(() => new Map(graph.nodes.map(n => [n.entity_id, n])), [graph]);
  const degree = useMemo(() => {
    const d = new Map();
    for (const e of graph.edges) { d.set(e.head, (d.get(e.head)||0)+1); d.set(e.tail, (d.get(e.tail)||0)+1); }
    return d;
  }, [graph]);
  const adjacency = useMemo(() => buildAdjacency(graph.edges), [graph]);

  const hubList = useMemo(() => {
    let ns = graph.nodes;
    if (typeFacet !== "ALL") ns = ns.filter(n => n.type === typeFacet);
    return [...ns].sort((a, b) => (degree.get(b.entity_id)||0) - (degree.get(a.entity_id)||0)).slice(0, 30);
  }, [graph, degree, typeFacet]);

  const ego = useMemo(() => {
    if (!focusId || !nodesById.has(focusId)) return { nodes:[], edges:[] };
    const { nodeIds, edges } = egoSubgraph(adjacency, focusId, hops, budget);
    return { nodes:[...nodeIds].map(id => nodesById.get(id)).filter(Boolean), edges };
  }, [adjacency, focusId, hops, budget, nodesById]);

  const neighbors = useMemo(() => {
    if (!selectedId) return [];
    const list = (adjacency.get(selectedId) || []).map(e => {
      const other = e.head === selectedId ? e.tail : e.head;
      const dir = e.head === selectedId ? "out" : "in";
      return { other, relation:e.relation, dir, node:nodesById.get(other) };
    }).filter(x => x.node);
    list.sort((a, b) => (degree.get(b.other)||0) - (degree.get(a.other)||0));
    return list.slice(0, 20);
  }, [adjacency, selectedId, nodesById, degree]);

  const loadDetail = useCallback(id => {
    setDetail(null); setSelectedEdge(null);
    getJSON(`${basePath}/node/${encodeURIComponent(id)}`).then(setDetail);
  }, [basePath]);
  // Raw recenter (no stack bookkeeping) -- shared by selectFocus (pushes first) and
  // goBack (pops instead of pushing) so the actual "move the focus" logic lives once.
  const goToFocus = useCallback(id => {
    setFocusId(id); setSelectedId(id); loadDetail(id);
  }, [loadDetail]);
  // Recenter: rebuilds the ego subgraph around id (used by sidebar/search navigation
  // and the explicit "设为中心" action — a deliberate jump, not an accidental one).
  const selectFocus = useCallback(id => {
    setFocusStack(prev => (focusId && focusId !== id) ? [...prev, focusId] : prev);
    goToFocus(id);
  }, [goToFocus, focusId]);
  // Pops the last pushed focus and jumps back to it, without re-pushing the current one.
  const goBack = useCallback(() => {
    setFocusStack(prev => {
      if (!prev.length) return prev;
      goToFocus(prev[prev.length - 1]);
      return prev.slice(0, -1);
    });
  }, [goToFocus]);
  // Inspect: highlights id within the *current* subgraph without recentering it —
  // used when clicking a node directly in the canvas, so the view never jumps.
  // Also useCallback'd (stable ref) so GraphCanvas — memo()'d, and the heaviest
  // component here — doesn't re-render on every unrelated state change (e.g. the
  // resize handles' width state updating on every drag mousemove).
  const inspectNode = useCallback(id => {
    setSelectedId(id); loadDetail(id);
  }, [loadDetail]);
  // Edges have no dedicated detail API — everything needed (relation + endpoint
  // name/type) is already in the ego subgraph data, so render it locally instead.
  const inspectEdge = useCallback(e => {
    setSelectedEdge(e); setDetail(null);
  }, []);

  // Reuses the hybrid retrieval module (lexical + semantic + graph fusion) just for
  // name resolution here -- expand=0 skips graph-pattern search/LLM summarization
  // (that belongs to the 检索 page), this only needs a ranked candidate list to jump to.
  const runSearch = () => {
    if (!searchTerm.trim() || !dataset) return;
    setSearching(true);
    getJSON(`/api/kg/retrieval/search?dataset=${dataset}&merge=${merge}&term=${encodeURIComponent(searchTerm.trim())}&top_k=10&expand=0`)
      .then(r => { setSearchResults(r.candidates); setSearching(false); })
      .catch(() => setSearching(false));
  };
  const pickSearchResult = (entityId) => {
    selectFocus(entityId);
    setSearchResults(null);
    setSearchTerm("");
  };
  const openDoc = (doc_id, matchNames) => {
    setDocMatch(matchNames); setDocLoading(true); setDocView(null);
    getJSON(`${basePath}/doc/${encodeURIComponent(doc_id)}`).then(d => { setDocView(d); setDocLoading(false); });
  };
  const closeDoc = () => { setDocView(null); setDocLoading(false); };

  const stats = graph.stats || {};
  const typeCounts = stats.type_counts || {};
  const focusNode = focusId ? nodesById.get(focusId) : null;
  const selectedNode = selectedId ? nodesById.get(selectedId) : null;

  return (
    <>
      <TopBar route="graph" />
      <div className="explorer">
        <div className="explorer-top">
          <select className="dataset-select" value={selectedKey || ""} onChange={e => setSelectedKey(e.target.value)}>
            {mergedList.map(m => (
              <option key={mergeKey(m)} value={mergeKey(m)}>{mergeLabel(m)}</option>
            ))}
          </select>
          <div className="search-box" style={{ position: "relative" }}>
            <input value={searchTerm} onChange={e => setSearchTerm(e.target.value)} placeholder="搜索实体，如 感冒 / 麻黄汤"
                   onKeyDown={e => e.key === "Enter" && runSearch()} disabled={searching} style={{ width:200 }} />
            <button className="primary" onClick={runSearch} disabled={searching}>{searching ? "…" : "搜索"}</button>
            {searchResults && (
              <div className="res-box" style={{ position: "absolute", top: "100%", left: 0, zIndex: 10, width: 280, marginTop: 4 }}>
                {searchResults.length === 0 ? (
                  <div className="hint" style={{ padding: 8 }}>未命中任何实体。</div>
                ) : searchResults.map(c => (
                  <div key={c.entity_id} className="res-item clickable" onClick={() => pickSearchResult(c.entity_id)}>
                    <span><b style={{ color: colorForType(c.type) }}>{c.name}</b><span className="muted"> （{labelForType(c.type)}）</span></span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="stats-row">
            <StatTile label="实体" value={stats.n_nodes ?? "—"} />
            <StatTile label="关系" value={stats.n_edges ?? "—"} />
            <StatTile label="来源文档" value={stats.n_docs ?? "—"} />
            <StatTile label="类型数" value={Object.keys(typeCounts).length || "—"} />
          </div>
          <div className="spacer" />
          <span className="hint">跨文档按“同名 + 同类型”对齐合并；图太大不适合整体渲染，右侧改为聚焦某实体查看其局部关系网络。</span>
        </div>

        <div className="explorer-body" style={{ gridTemplateColumns: `${leftW}px 6px 1fr 6px ${rightW}px` }}>
          <aside className="rail">
            <div>
              <h3>热门实体（按连接数排序）</h3>
              <div className="rank-list">
                {hubList.map(n => (
                  <div key={n.entity_id} className={"rank-item" + (n.entity_id === selectedId ? " active" : "")} onClick={() => selectFocus(n.entity_id)}>
                    <span className="dot" style={{ background: colorForType(n.type) }} />
                    <span className="name">{n.name}</span>
                    <span className="metric">{degree.get(n.entity_id) || 0}</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h3>实体类型分布（点击筛选）</h3>
              <TypeBarChart counts={typeCounts} active={typeFacet} onPick={t => setTypeFacet(t === typeFacet ? "ALL" : t)} />
            </div>
          </aside>

          <ResizeHandle onMouseDown={leftDrag} />

          <section className="canvas-col">
            <div className="canvas-toolbar">
              {focusStack.length > 0 && (
                <button className="link" onClick={goBack} style={{ marginRight: 10 }}>← 返回</button>
              )}
              {focusNode
                ? <span className="focus-label">聚焦 <b style={{ color: colorForType(focusNode.type) }}>{focusNode.name}</b> <span className="muted">（{labelForType(focusNode.type)}）</span></span>
                : <span className="muted">从左侧选择实体查看其关系网络</span>}
              {selectedNode && selectedId !== focusId && (
                <span className="focus-label">· 已选中 <b style={{ color: colorForType(selectedNode.type) }}>{selectedNode.name}</b>
                  <button className="link" style={{ marginLeft:8 }} onClick={() => selectFocus(selectedId)}>设为中心 →</button>
                </span>
              )}
              <div className="spacer" />
              <label>跳数
                <span className="seg">
                  {[1,2,3].map(h => <button key={h} className={"seg-btn" + (hops === h ? " on" : "")} onClick={() => setHops(h)}>{h}</button>)}
                </span>
              </label>
              <label>节点上限 {budget}
                <input type="range" min="10" max="240" step="10" value={budget} onChange={e => setBudget(+e.target.value)} style={{ width:100 }} />
              </label>
              <span className="muted">{ego.nodes.length} 节点 / {ego.edges.length} 边</span>
            </div>
            <div className="canvas">
              {loading ? <div className="empty">加载图谱中…</div>
                : ego.nodes.length === 0 ? <div className="empty">从左侧选择一个实体开始探索</div>
                : <GraphCanvas nodes={ego.nodes} edges={ego.edges} onSelectNode={inspectNode} onSelectEdge={inspectEdge} centerId={focusId} highlightId={selectedId} />}
            </div>
            <div className="hint" style={{ padding:"6px 16px" }}>图中点击节点/边可在右侧查看详情，不会重新布局；左侧列表点击或“设为中心”会重新聚焦。</div>
          </section>

          <ResizeHandle onMouseDown={rightDrag} />

          <aside className="rail right">
            {selectedEdge ? (() => {
              const h = nodesById.get(selectedEdge.head), t = nodesById.get(selectedEdge.tail);
              return (
                <div className="detail">
                  <div className="detail-head">关系详情</div>
                  <div className="row"><span className="k">关系</span>{selectedEdge.relation}</div>
                  {selectedEdge.condition && (
                    <div className="row"><span className="k">触发条件</span>{selectedEdge.condition}</div>
                  )}
                  <div className="row">
                    <span className="k">头实体</span>
                    <span style={{ color: colorForType(h?.type) }}>{h?.name || selectedEdge.head}</span>
                    <span className="muted"> （{labelForType(h?.type)}）</span>
                  </div>
                  <div className="row">
                    <span className="k">尾实体</span>
                    <span style={{ color: colorForType(t?.type) }}>{t?.name || selectedEdge.tail}</span>
                    <span className="muted"> （{labelForType(t?.type)}）</span>
                  </div>
                  {h && <button className="link" onClick={() => selectFocus(h.entity_id)}>查看头实体详情 →</button>}
                  {t && <div><button className="link" onClick={() => selectFocus(t.entity_id)}>查看尾实体详情 →</button></div>}
                </div>
              );
            })() : !detail ? <div className="hint">点击左侧实体、搜索结果或图中节点/边，查看详情、相关实体与来源文档。</div> : (
              <div className="detail">
                <div className="detail-head">
                  <span style={{ color: colorForType(detail.type) }}>{detail.name}</span>
                  <span className="type-badge" style={{ color: colorForType(detail.type) }}>{labelForType(detail.type)}</span>
                </div>
                <div className="row">连接数 <b>{degree.get(detail.entity_id) || 0}</b> · 出现于 <b>{detail.source_doc_ids?.length || 0}</b> 篇文档</div>
                {detail.aliases?.length > 0 && <div className="row"><span className="k">别名</span>{detail.aliases.slice(0, 8).join("、")}</div>}
                {Object.keys(detail.attributes || {}).length > 0 && (
                  <div className="attr-list">
                    {Object.entries(detail.attributes).map(([k, v]) => (
                      <div className="row" key={k}><span className="k">{k}</span>{v.join("、")}</div>
                    ))}
                  </div>
                )}

                {neighbors.length > 0 && (
                  <div>
                    <h3>相关实体</h3>
                    <div className="rank-list">
                      {neighbors.map((nb, i) => (
                        <div key={i} className="rank-item" onClick={() => selectFocus(nb.other)}>
                          <span className="dot" style={{ background: colorForType(nb.node.type) }} />
                          <span className="name">{nb.dir === "out" ? "→ " : "← "}{nb.node.name}</span>
                          <span className="metric rel">{nb.relation}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <h3 style={{ marginTop:16 }}>来源分析（{detail.sources?.length || 0} 篇文档）</h3>
                <div className="src-list">
                  {(detail.sources || []).slice(0, 30).map(s => (
                    <div className="src" key={s.doc_id} onClick={() => openDoc(s.doc_id, [detail.name, ...(detail.aliases||[])])}>
                      <div className="t">{s.doc_id}{s.title ? " · " + s.title : ""}</div>
                      <div className="snip">{s.snippet}</div>
                      <div className="more">查看该文档的完整抽取结果 →</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </aside>
        </div>
      </div>

      {(docLoading || docView) && (
        <div className="modal-backdrop" onClick={closeDoc}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <button className="link" onClick={closeDoc}>← 返回</button>
              <span className="modal-title">{docView ? `${docView.doc_id}${docView.title ? " · " + docView.title : ""}` : "加载中…"}</span>
              <div className="spacer" />
              {docView && <span className="muted">来源切分：{selected ? mergeLabel(selected) : dataset}/{docView.split}</span>}
            </div>
            {docLoading || !docView
              ? <div className="empty">加载文档抽取结果…</div>
              : <DocExtractionView doc={docView} matchNames={docMatch} />}
          </div>
        </div>
      )}
    </>
  );
}
