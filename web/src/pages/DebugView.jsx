import { useCallback, useEffect, useMemo, useState } from "react";
import { TopBar } from "../components/TopBar.jsx";
import { GraphCanvas } from "../components/GraphCanvas.jsx";
import { ResizeHandle } from "../components/ResizeHandle.jsx";
import { DocList } from "../components/DocList.jsx";
import { TextPanel } from "../components/TextPanel.jsx";
import { useResizer } from "../hooks/useResizer.js";
import { getJSON } from "../utils/api.js";
import { colorForType, labelForType } from "../utils/types.js";

/* ---------- 细节调试 ---------- */
export function DebugView() {
  const [datasets, setDatasets] = useState([]);
  const [dataset, setDataset] = useState("docred");
  const [split, setSplit] = useState("eval200");
  const [docs, setDocs] = useState([]);
  const [docId, setDocId] = useState(null);
  const [doc, setDoc] = useState(null);
  const [selected, setSelected] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [w1, drag1] = useResizer(420, { min: 280, max: 720 });
  const [w2, drag2] = useResizer(480, { min: 280, max: 1400 });

  useEffect(() => {
    getJSON("/api/datasets").then(ds => {
      setDatasets(ds);
      if (ds.length) { setDataset(ds[0].dataset); setSplit(ds[0].split); }
    });
  }, []);

  useEffect(() => {
    if (!dataset || !split) return;
    setDocId(null); setDoc(null); setSelected(null); setSelectedEdge(null);
    getJSON(`/api/docs?dataset=${dataset}&split=${split}`).then(setDocs);
  }, [dataset, split]);

  const loadDoc = useCallback((id, focusEntity = null) => {
    setDocId(id); setSelected(focusEntity); setSelectedEdge(null);
    getJSON(`/api/doc/${dataset}/${split}/${id}`).then(setDoc);
  }, [dataset, split]);
  const selectNode = useCallback(id => { setSelected(id); setSelectedEdge(null); }, []);
  const selectEdge = useCallback(e => { setSelectedEdge(e); setSelected(null); }, []);

  const mentionByEntity = useMemo(() => {
    if (!doc) return {};
    const m = {};
    for (const n of doc.nodes) for (const mid of n.mention_ids || []) m[mid] = n.entity_id;
    return m;
  }, [doc]);

  const entityById = useMemo(() => {
    if (!doc) return {};
    return Object.fromEntries(doc.nodes.map(n => [n.entity_id, n]));
  }, [doc]);

  const selectedNode = selected ? entityById[selected] : null;

  const search = () => {
    getJSON(`/api/search?dataset=${dataset}&split=${split}&q=${encodeURIComponent(query)}`).then(setResults);
  };

  // Memoized (not just computed inline) so its array reference stays stable across
  // unrelated re-renders (e.g. resize-dragging w1/w2) — TextPanel is memo()'d and
  // would otherwise re-diff every mention span on every one of those renders.
  const textSpans = useMemo(() => {
    if (!doc) return [];
    const out = [];
    const ms = [...doc.mentions].filter(m => m.char_start != null && m.char_end != null).sort((a, b) => a.char_start - b.char_start);
    let cursor = 0;
    for (const m of ms) {
      if (m.char_start < cursor) continue;
      if (m.char_start > cursor) out.push({ text: doc.text.slice(cursor, m.char_start), mention:null });
      out.push({ text: doc.text.slice(m.char_start, m.char_end), mention:m });
      cursor = m.char_end;
    }
    if (cursor < doc.text.length) out.push({ text: doc.text.slice(cursor), mention:null });
    return out;
  }, [doc]);

  const datasetOptions = useMemo(() => [...new Set(datasets.map(d => d.dataset))], [datasets]);
  const splitOptions = useMemo(() => datasets.filter(d => d.dataset === dataset), [datasets, dataset]);

  const changeDataset = ds => {
    setDataset(ds);
    const first = datasets.find(d => d.dataset === ds);
    setSplit(first ? first.split : "");
  };

  return (
    <>
      <TopBar route="debug" />
      <div className="debug-top">
        <label className="muted">数据集
          <select value={dataset} onChange={e => changeDataset(e.target.value)} style={{ marginLeft:6 }}>
            {datasetOptions.map(ds => <option key={ds} value={ds}>{ds}</option>)}
          </select>
        </label>
        <label className="muted">切分
          <select value={split} onChange={e => setSplit(e.target.value)} style={{ marginLeft:6 }}>
            {splitOptions.map(d => <option key={d.split} value={d.split}>{d.split}（{d.n_docs} 篇，已抽取 {d.n_extracted}）</option>)}
          </select>
        </label>
        <span className="muted">文档列表最多显示 1234 篇（当前 {docs.length} 篇，已抽取优先排前）</span>
      </div>
      <main style={{ gridTemplateColumns: `${w1}px 6px ${w2}px 6px 1fr` }}>
        <section className="panel">
          <h2>原文视图（高亮可点）</h2>
          <DocList docs={docs} docId={docId} onSelect={loadDoc} />
          <TextPanel
            textSpans={textSpans}
            selected={selected}
            mentionByEntity={mentionByEntity}
            entityById={entityById}
            onSelectMention={selectNode}
            unextracted={!!(doc && doc.nodes.length === 0)}
          />
        </section>

        <ResizeHandle onMouseDown={drag1} />

        <section className="panel">
          <h2>图谱视图（点击节点/边展开详情）</h2>
          {doc && doc.nodes.length > 0 && (
            <GraphCanvas nodes={doc.nodes} edges={doc.edges} onSelectNode={selectNode} onSelectEdge={selectEdge} centerId={null} highlightId={selected} />
          )}
          {doc && doc.nodes.length === 0 && <div className="empty">该文档尚未运行实体抽取（stage1），暂无图谱。</div>}
          {!doc && <div className="empty">加载文档后显示图谱。</div>}
          {selectedNode && (
            <div className="node-detail">
              <div><span style={{ color: colorForType(selectedNode.type) }}>{selectedNode.name}</span> <span className="k">（{labelForType(selectedNode.type)}）</span></div>
              {selectedNode.aliases?.length > 0 && <div className="k">别名: {selectedNode.aliases.join("、")}</div>}
              {Object.keys(selectedNode.attributes || {}).length > 0 && (
                <div>
                  {Object.entries(selectedNode.attributes).map(([k, v]) => (
                    <div key={k}><span className="k">{k}:</span> {v.join("、")}</div>
                  ))}
                </div>
              )}
            </div>
          )}
          {selectedEdge && (() => {
            const h = entityById[selectedEdge.head], t = entityById[selectedEdge.tail];
            return (
              <div className="node-detail">
                <div><span className="k">关系</span> {selectedEdge.relation}</div>
                <div>
                  <span style={{ color: colorForType(h?.type) }}>{h?.name || selectedEdge.head}</span>
                  <span className="k"> （{labelForType(h?.type)}） → {selectedEdge.relation} → </span>
                  <span style={{ color: colorForType(t?.type) }}>{t?.name || selectedEdge.tail}</span>
                  <span className="k"> （{labelForType(t?.type)}）</span>
                </div>
              </div>
            );
          })()}
        </section>

        <ResizeHandle onMouseDown={drag2} />

        <section className="panel">
          <h2>检索面板</h2>
          <div className="retrieval">
            <div className="callout">
              <b>三种检索并行跑，结果分框展示：</b><br />
              · <b>语义检索·节点</b>：把查询转成向量，找含义最接近的实体；<br />
              · <b>语义检索·段落</b>：找含义最接近的原文段落；<br />
              · <b>词法匹配</b>：按实体名字面相似度（编辑距离）匹配；<br />
              · <b>图搜索</b>：从语义命中的实体出发，沿关系走 2 步扩展，直接列出扩展到的关系事实。<br />
              百分比 = 相似度分数，越高越接近查询。<b>点击任意结果</b>可跳转到其原文并在左侧高亮、在图谱中选中对应节点。
            </div>
            <div className="qrow">
              <input value={query} onChange={e => setQuery(e.target.value)} placeholder="输入查询，如：Who founded Harvard?" onKeyDown={e => e.key === "Enter" && search()} />
              <button className="primary" onClick={search}>检索</button>
            </div>
            {results && (
              <div className="cols">
                <div>
                  <div className="res-box">
                    <h3>语义检索 · 节点</h3>
                    {results.semantic.nodes.map((n, i) => (
                      <div className="res-item clickable" key={i} onClick={() => loadDoc(n.doc_id, n.entity_id)}>
                        <b style={{ color: colorForType(n.type) }}>{n.name}</b> <span className="score">{(n.score*100).toFixed(0)}%</span>
                      </div>
                    ))}
                    {results.semantic.nodes.length === 0 && <div className="hint">无匹配结果</div>}
                  </div>
                  <div className="res-box">
                    <h3>语义检索 · 段落</h3>
                    {results.semantic.passages.map((p, i) => (
                      <div className="res-item clickable" key={i} onClick={() => loadDoc(p.doc_id)}>
                        {p.text.slice(0, 80)}… <span className="score">{(p.score*100).toFixed(0)}%</span>
                      </div>
                    ))}
                    {results.semantic.passages.length === 0 && <div className="hint">无匹配结果</div>}
                  </div>
                </div>
                <div>
                  <div className="res-box">
                    <h3>词法匹配</h3>
                    {results.lexical.map((n, i) => (
                      <div className="res-item clickable" key={i} onClick={() => loadDoc(n.doc_id, n.entity_id)}>
                        <b style={{ color: colorForType(n.type) }}>{n.name}</b> <span className="score">{(n.score*100).toFixed(0)}%</span>
                      </div>
                    ))}
                    {results.lexical.length === 0 && <div className="hint">无匹配结果</div>}
                  </div>
                  <div className="res-box">
                    <h3>图搜索 · 关系事实（{results.graph.nodes.length} 节点 / {results.graph.edges.length} 条关系）</h3>
                    {(() => {
                      const gmap = Object.fromEntries(results.graph.nodes.map(n => [n.entity_id, n]));
                      const triples = results.graph.edges.map(e => ({ ...e, h: gmap[e.head], t: gmap[e.tail] })).filter(e => e.h && e.t);
                      return triples.length > 0 ? triples.slice(0, 20).map((e, i) => (
                        <div className="res-item clickable" key={i} onClick={() => loadDoc(e.h.doc_id, e.h.entity_id)}>
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
              </div>
            )}
          </div>
        </section>
      </main>
    </>
  );
}
