import { useCallback, useEffect, useMemo, useState } from "react";
import { diffArrays } from "diff";
import { TopBar } from "../components/TopBar.jsx";
import { StatTile } from "../components/StatTile.jsx";
import { ResizeHandle } from "../components/ResizeHandle.jsx";
import { useResizer } from "../hooks/useResizer.js";
import { getJSON } from "../utils/api.js";

function SplitPicker({ splits, dataset, split, onPick }) {
  return (
    <select
      className="dataset-select"
      value={dataset && split ? `${dataset}::${split}` : ""}
      onChange={e => { const [d, s] = e.target.value.split("::"); onPick(d, s); }}
    >
      {splits.map(s => (
        <option key={`${s.dataset}::${s.split}`} value={`${s.dataset}::${s.split}`}>
          {s.dataset} / {s.split}（{s.n_docs} 篇）
        </option>
      ))}
    </select>
  );
}

// normalize.py deliberately collapses 、/， to a halfwidth "," (and ：；（） to their
// halfwidth forms) before the text ever reaches the LLM, but the model writes its output
// in ordinary modern-Chinese fullwidth punctuation -- a naive diff would flag nearly
// every comma/colon as changed, burying real content edits under punctuation-width
// noise. Every diff below (sentence-level pairing AND the intra-sentence char diff)
// shares this same equivalence so that noise never appears at either granularity.
const PUNCT_GROUPS = [[",", "，", "、"], [":", "："], [";", "；"], ["(", "（"], [")", "）"]];
const PUNCT_CANON = new Map(PUNCT_GROUPS.flatMap(g => g.map(ch => [ch, g[0]])));
const canon = ch => PUNCT_CANON.get(ch) ?? ch;
const canonize = s => Array.from(s).map(canon).join("");
const charsEqual = (a, b) => canon(a) === canon(b);

// Split on Chinese sentence terminators (keeping the terminator with the sentence it
// ends), purely for *display* line-breaking -- this has nothing to do with how
// simplify.py calls the LLM (one call per whole doc, see that module).
const SENTENCE_SPLIT_RE = /(?<=[。！？；])/;
function splitSentences(text) {
  return (text || "").split(SENTENCE_SPLIT_RE).map(s => s.trim()).filter(Boolean);
}

function charDiffCounts(before, after) {
  const parts = diffArrays(Array.from(before || ""), Array.from(after || ""), { comparator: charsEqual });
  let added = 0, removed = 0;
  for (const part of parts) {
    if (part.added) added += part.value.length;
    else if (part.removed) removed += part.value.length;
  }
  return { added, removed };
}

// Pairs original/translated sentences left-right for a side-by-side view, the way a
// split diff tool lines up old/new lines: unchanged sentences align 1:1, a removed
// block immediately followed by an added block is treated as "these sentences turned
// into those sentences" and paired index-wise (a doc often gets re-split into a
// different number of sentences, so this is an approximation, not a semantic match),
// and anything left over renders as a delete-only or insert-only row.
function pairSentenceRows(originalText, simplifiedText) {
  const oldSents = splitSentences(originalText);
  const newSents = splitSentences(simplifiedText);
  const parts = diffArrays(oldSents, newSents, { comparator: (a, b) => canonize(a) === canonize(b) });
  const rows = [];
  let i = 0;
  while (i < parts.length) {
    const part = parts[i];
    if (!part.added && !part.removed) {
      for (const s of part.value) rows.push({ left: s, right: s, changed: false });
      i += 1;
      continue;
    }
    if (part.removed) {
      const next = parts[i + 1];
      const addedArr = next && next.added ? next.value : [];
      const n = Math.max(part.value.length, addedArr.length);
      for (let k = 0; k < n; k++) rows.push({ left: part.value[k] ?? null, right: addedArr[k] ?? null, changed: true });
      i += next && next.added ? 2 : 1;
      continue;
    }
    for (const s of part.value) rows.push({ left: null, right: s, changed: true });
    i += 1;
  }
  return rows;
}

function InlineDiff({ parts, side }) {
  const cls = side === "left" ? p => (p.removed ? "diff-del" : undefined) : p => (p.added ? "diff-add" : undefined);
  const visible = side === "left" ? parts.filter(p => !p.added) : parts.filter(p => !p.removed);
  return visible.map((p, i) => <span key={i} className={cls(p)}>{p.value}</span>);
}

function DiffRow({ left, right, changed }) {
  if (!changed) {
    return (
      <div className="diff-row">
        <div className="diff-cell">{left}</div>
        <div className="diff-cell">{right}</div>
      </div>
    );
  }
  if (left != null && right != null) {
    const parts = diffArrays(Array.from(left), Array.from(right), { comparator: charsEqual })
      .map(p => ({ ...p, value: p.value.join("") }));
    return (
      <div className="diff-row changed">
        <div className="diff-cell"><InlineDiff parts={parts} side="left" /></div>
        <div className="diff-cell"><InlineDiff parts={parts} side="right" /></div>
      </div>
    );
  }
  return (
    <div className="diff-row changed">
      <div className="diff-cell">{left != null && <span className="diff-del">{left}</span>}</div>
      <div className="diff-cell">{right != null && <span className="diff-add">{right}</span>}</div>
    </div>
  );
}

function DocDiff({ doc }) {
  const rows = useMemo(() => pairSentenceRows(doc.original_text, doc.simplified_text), [doc]);
  if (!doc.simplified_text) {
    return <div className="hint" style={{ padding: 12 }}>无输出（模型多次重试后仍未返回内容）</div>;
  }
  return rows.map((r, i) => <DiffRow key={i} left={r.left} right={r.right} changed={r.changed} />);
}

/* ---------- 预处理审阅：原文 -> 文言翻译/指代消解，逐句左右对照（整篇一次翻译） ---------- */
export function Preprocess() {
  const [splits, setSplits] = useState([]);
  const [dataset, setDataset] = useState(null);
  const [split, setSplit] = useState(null);
  const [docs, setDocs] = useState([]);
  const [docId, setDocId] = useState(null);
  const [doc, setDoc] = useState(null);
  const [w1, drag1] = useResizer(300, { min: 220, max: 480 });

  useEffect(() => {
    getJSON("/api/preprocess/splits").then(rows => {
      setSplits(rows);
      if (rows.length) { setDataset(rows[0].dataset); setSplit(rows[0].split); }
    });
  }, []);

  useEffect(() => {
    if (!dataset || !split) return;
    setDocId(null); setDoc(null);
    getJSON(`/api/preprocess/docs?dataset=${dataset}&split=${split}`).then(setDocs);
  }, [dataset, split]);

  const loadDoc = useCallback(id => {
    setDocId(id);
    getJSON(`/api/preprocess/doc/${dataset}/${split}/${id}`).then(setDoc);
  }, [dataset, split]);

  const current = splits.find(s => s.dataset === dataset && s.split === split);

  const docDiffStats = useMemo(() => {
    if (!doc || !doc.simplified_text) return null;
    return charDiffCounts(doc.original_text, doc.simplified_text);
  }, [doc]);

  return (
    <>
      <TopBar route="preprocess" />
      <div className="explorer">
      <div className="explorer-top">
        {splits.length > 0 && <SplitPicker splits={splits} dataset={dataset} split={split} onPick={(d, s) => { setDataset(d); setSplit(s); }} />}
        {current && (
          <div className="stats-row">
            <StatTile label="文档" value={current.n_docs} />
            {docDiffStats && <StatTile label="本篇新增字数" value={docDiffStats.added} />}
            {docDiffStats && <StatTile label="本篇删除字数" value={docDiffStats.removed} />}
          </div>
        )}
      </div>

      {splits.length === 0 ? (
        <div className="empty">还没有任何 split 跑过 preprocess/simplify.py（找不到 simplified.jsonl）</div>
      ) : (
        <div className="explorer-body" style={{ gridTemplateColumns: `${w1}px auto 1fr` }}>
          <div className="doc-list" style={{ maxHeight: "none", overflow: "auto" }}>
            {docs.map(d => (
              <div key={d.doc_id} className={"doc-item" + (d.doc_id === docId ? " active" : "")} onClick={() => loadDoc(d.doc_id)}>
                <b>{d.doc_id}</b> — {d.title}
              </div>
            ))}
            {docs.length === 0 && <div className="hint" style={{ padding: 12 }}>没有文档。</div>}
          </div>
          <ResizeHandle onMouseDown={drag1} />
          <div className="para-scroll">
            {!doc && <div className="empty">选择左侧文档查看逐句对照</div>}
            {doc && (
              <>
                <h2 className="doc-title">
                  {doc.doc_id} · {doc.title}
                  {doc.context && <span className="chip" style={{ marginLeft: 10 }}>{doc.context}</span>}
                </h2>
                <div className="diff-col-headers">
                  <div>原文</div>
                  <div>翻译后</div>
                </div>
                <div className="para-list">
                  <DocDiff doc={doc} />
                </div>
              </>
            )}
          </div>
        </div>
      )}
      </div>
    </>
  );
}
