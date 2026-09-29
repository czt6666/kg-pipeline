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
  const [w1, drag1] = useResizer(420, { min: 280, max: 720 });

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

  // Memoized (not just computed inline) so its array reference stays stable across
  // unrelated re-renders (e.g. resize-dragging w1) — TextPanel is memo()'d and
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
      <main style={{ gridTemplateColumns: `${w1}px 6px 1fr` }}>
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
      </main>
    </>
  );
}
