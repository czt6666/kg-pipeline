import { useCallback, useEffect, useState } from "react";
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
          {s.dataset} / {s.split}（{s.n_pages} 页）
        </option>
      ))}
    </select>
  );
}

/* ---------- 流水线第一步：OCR 原文，按页浏览 stage0_ocr.py 的原始识别结果 ---------- */
export function OcrView() {
  const [splits, setSplits] = useState([]);
  const [dataset, setDataset] = useState(null);
  const [split, setSplit] = useState(null);
  const [pages, setPages] = useState([]);
  const [pageIndex, setPageIndex] = useState(null);
  const [page, setPage] = useState(null);
  const [w1, drag1] = useResizer(280, { min: 200, max: 420 });

  useEffect(() => {
    getJSON("/api/ocr/splits").then(rows => {
      setSplits(rows);
      if (rows.length) { setDataset(rows[0].dataset); setSplit(rows[0].split); }
    });
  }, []);

  useEffect(() => {
    if (!dataset || !split) return;
    setPageIndex(null); setPage(null);
    getJSON(`/api/ocr/pages?dataset=${dataset}&split=${split}`).then(setPages);
  }, [dataset, split]);

  const loadPage = useCallback(idx => {
    setPageIndex(idx);
    getJSON(`/api/ocr/page/${dataset}/${split}/${idx}`).then(setPage);
  }, [dataset, split]);

  const current = splits.find(s => s.dataset === dataset && s.split === split);

  return (
    <>
      <TopBar route="ocr" />
      <div className="explorer">
      <div className="explorer-top">
        {splits.length > 0 && <SplitPicker splits={splits} dataset={dataset} split={split} onPick={(d, s) => { setDataset(d); setSplit(s); }} />}
        {current && (
          <div className="stats-row">
            <StatTile label="页数" value={current.n_pages} />
          </div>
        )}
      </div>

      {splits.length === 0 ? (
        <div className="empty">还没有任何 split 跑过 stage0_ocr.py（找不到 ocr_pages.jsonl）</div>
      ) : (
        <div className="explorer-body" style={{ gridTemplateColumns: `${w1}px auto 1fr` }}>
          <div className="doc-list" style={{ maxHeight: "none", overflow: "auto" }}>
            {pages.map(p => (
              <div key={p.page_index} className={"doc-item" + (p.page_index === pageIndex ? " active" : "")} onClick={() => loadPage(p.page_index)}>
                <b>第 {p.page_index} 页</b> — {p.preview}
              </div>
            ))}
            {pages.length === 0 && <div className="hint" style={{ padding: 12 }}>没有页面。</div>}
          </div>
          <ResizeHandle onMouseDown={drag1} />
          <div className="para-scroll">
            {!page && <div className="empty">选择左侧页面查看 OCR 原文</div>}
            {page && (
              <>
                <h2 className="doc-title">第 {page.page_index} 页</h2>
                <pre className="ocr-text">{page.text}</pre>
              </>
            )}
          </div>
        </div>
      )}
      </div>
    </>
  );
}
