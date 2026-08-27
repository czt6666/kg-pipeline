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

/* ---------- 完整知识图谱 ---------- */
export function GraphExplorer() {
  const [mergedList, setMergedList] = useState([]);
  const [dataset, setDataset] = useState(null);
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
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [leftW, leftDrag] = useResizer(280, { min: 220, max: 480 });
  const [rightW, rightDrag] = useResizer(340, { min: 260, max: 560, invert: true });

  useEffect(() => {
    getJSON("/api/merged").then(list => {
      setMergedList(list);
      if (list.length) setDataset(list[0].dataset);
    });
  }, []);

  useEffect(() => {
    if (!dataset) return;
    setLoading(true); setFocusId(null); setSelectedId(null); setDetail(null); setSelectedEdge(null); setSearchResults(null); setSearching(false); setQuery(""); setTypeFacet("ALL"); setDocView(null);
    getJSON(`/api/merged/${dataset}`).then(g => {
      setGraph(g);
      setLoading(false);
      const deg = {};
      for (const e of g.edges) { deg[e.head] = (deg[e.head]||0)+1; deg[e.tail] = (deg[e.tail]||0)+1; }
      let top = null, topDeg = -1;
      for (const n of g.nodes) { const d = deg[n.entity_id]||0; if (d > topDeg) { topDeg = d; top = n.entity_id; } }
      if (top) { setFocusId(top); setSelectedId(top); }
    });
  }, [dataset]);

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
    getJSON(`/api/merged/${dataset}/node/${encodeURIComponent(id)}`).then(setDetail);
  }, [dataset]);
  // Recenter: rebuilds the ego subgraph around id (used by sidebar/search navigation
  // and the explicit "设为中心" action — a deliberate jump, not an accidental one).
  const selectFocus = useCallback(id => {
    setFocusId(id); setSelectedId(id); loadDetail(id);
  }, [loadDetail]);
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
  const runSearch = () => {
    if (!query.trim()) { setSearchResults(null); return; }
    setSearching(true);
    getJSON(`/api/merged/${dataset}/search?q=${encodeURIComponent(query)}&top_k=15`)
      .then(r => { setSearchResults(r); setSearching(false); });
  };
  const openDoc = (doc_id, matchNames) => {
    setDocMatch(matchNames); setDocLoading(true); setDocView(null);
    getJSON(`/api/merged/${dataset}/doc/${encodeURIComponent(doc_id)}`).then(d => { setDocView(d); setDocLoading(false); });
  };
  const closeDoc = () => { setDocView(null); setDocLoading(false); };

  const stats = graph.stats || {};
  const typeCounts = stats.type_counts || {};
  const relationCounts = Object.entries(stats.relation_counts || {}).slice(0, 8);
  const focusNode = focusId ? nodesById.get(focusId) : null;
  const selectedNode = selectedId ? nodesById.get(selectedId) : null;

  return (
    <>
      <TopBar route="graph" />
      <div className="explorer">
        <div className="explorer-top">
          <div className="dataset-pills">
            {mergedList.map(m => (
              <button key={m.dataset} className={"pill" + (m.dataset === dataset ? " active" : "")} onClick={() => setDataset(m.dataset)}>{m.dataset}</button>
            ))}
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
              <h3>搜索实体</h3>
              <div className="search-box">
                <input value={query} onChange={e => setQuery(e.target.value)} placeholder="如 United Kingdom"
                       onKeyDown={e => e.key === "Enter" && runSearch()} disabled={searching} />
                <button className="primary" onClick={runSearch} disabled={searching}>{searching ? "搜索中…" : "搜"}</button>
              </div>
            </div>

            {searching ? (
              <div className="hint">检索中…</div>
            ) : searchResults ? (
              <div>
                <div className="rail-row-head">
                  <h3>检索结果</h3>
                  <button className="link" onClick={() => { setSearchResults(null); setQuery(""); }}>清除 ×</button>
                </div>
                <div className="hint" style={{ marginBottom:8 }}>点击任意结果聚焦该实体并查看详情。</div>
                <div className="res-box">
                  <h3>语义检索 · 节点</h3>
                  {searchResults.semantic.nodes.map(n => (
                    <div key={n.entity_id} className={"res-item clickable" + (n.entity_id === selectedId ? " active" : "")} onClick={() => selectFocus(n.entity_id)}>
                      <b style={{ color: colorForType(n.type) }}>{n.name}</b> <span className="score">{(n.score*100).toFixed(0)}%</span>
                    </div>
                  ))}
                  {searchResults.semantic.nodes.length === 0 && <div className="hint">无匹配结果</div>}
                </div>
                {searchResults.semantic.passages?.length > 0 && (
                  <div className="res-box">
                    <h3>语义检索 · 段落</h3>
                    {searchResults.semantic.passages.map((p, i) => (
                      <div key={i} className="res-item">{p.text.slice(0, 60)}… <span className="score">{(p.score*100).toFixed(0)}%</span></div>
                    ))}
                  </div>
                )}
                <div className="res-box">
                  <h3>词法匹配</h3>
                  {searchResults.lexical.map(n => (
                    <div key={n.entity_id} className={"res-item clickable" + (n.entity_id === selectedId ? " active" : "")} onClick={() => selectFocus(n.entity_id)}>
                      <b style={{ color: colorForType(n.type) }}>{n.name}</b> <span className="score">{(n.score*100).toFixed(0)}%</span>
                    </div>
                  ))}
                  {searchResults.lexical.length === 0 && <div className="hint">无匹配结果</div>}
                </div>
                <div className="res-box">
                  <h3>图搜索 · 关系事实</h3>
                  {(() => {
                    const gmap = Object.fromEntries(searchResults.graph.nodes.map(n => [n.entity_id, n]));
                    const triples = searchResults.graph.edges.map(e => ({ ...e, h: gmap[e.head], t: gmap[e.tail] })).filter(e => e.h && e.t);
                    return triples.length > 0 ? triples.slice(0, 20).map((e, i) => (
                      <div className="res-item clickable" key={i} onClick={() => selectFocus(e.h.entity_id)}>
                        <span>
                          <b style={{ color: colorForType(e.h.type) }}>{e.h.name}</b>
                          <span className="muted"> —{e.relation}→ </span>
                          <b style={{ color: colorForType(e.t.type) }}>{e.t.name}</b>
                        </span>
                      </div>
                    )) : <div className="hint">未从命中实体扩展出新关系</div>;
                  })()}
                </div>
              </div>
            ) : (
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
            )}

            <div>
              <h3>实体类型分布（点击筛选）</h3>
              <TypeBarChart counts={typeCounts} active={typeFacet} onPick={t => setTypeFacet(t === typeFacet ? "ALL" : t)} />
            </div>

            {relationCounts.length > 0 && (
              <div>
                <h3>常见关系</h3>
                <div className="chips">
                  {relationCounts.map(([rel, c]) => <span className="chip" key={rel}>{rel} <b>{c}</b></span>)}
                </div>
              </div>
            )}
          </aside>

          <ResizeHandle onMouseDown={leftDrag} />

          <section className="canvas-col">
            <div className="canvas-toolbar">
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
              {docView && <span className="muted">来源切分：{dataset}/{docView.split}</span>}
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
