import { memo } from "react";

// Memoized: the panel widths (dragged via ResizeHandle) live in DebugView's state,
// so every resize-drag frame re-renders DebugView — without memoizing this list,
// that would re-diff up to DOC_LIST_LIMIT (1234) rows on every mousemove. `onSelect`
// must be a stable (useCallback'd) reference from the caller for this to help.
export const DocList = memo(function DocList({ docs, docId, onSelect }) {
  return (
    <div className="doc-list">
      {docs.map(d => (
        <div key={d.doc_id} className={"doc-item" + (d.doc_id === docId ? " active" : "") + (d.has_extraction ? "" : " unextracted")} onClick={() => onSelect(d.doc_id)}>
          {!d.has_extraction && <span className="unextracted-tag">未抽取</span>}
          <b>{d.doc_id}</b> — {d.preview}
        </div>
      ))}
      {docs.length === 0 && <div className="hint" style={{ padding:12 }}>该切分暂无数据。</div>}
    </div>
  );
});
