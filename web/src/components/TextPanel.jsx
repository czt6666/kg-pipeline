import { memo } from "react";
import { labelForType } from "../utils/types.js";

// Memoized for the same reason as DocList: resize-drag re-renders the parent view
// on every mousemove, and long documents can have hundreds of mention spans —
// no need to re-diff them unless the doc, selection, or highlight actually changed.
export const TextPanel = memo(function TextPanel({ textSpans, selected, mentionByEntity, entityById, onSelectMention, unextracted }) {
  return (
    <div className="text-view">
      {textSpans.length === 0 && <span className="hint">选择左侧文档查看原文。</span>}
      {unextracted && (
        <div className="callout" style={{ marginBottom:14 }}>该文档尚未运行实体抽取（stage1），下方为原文，暂无实体高亮。</div>
      )}
      {textSpans.map((s, i) => {
        if (!s.mention) return <span key={i}>{s.text}</span>;
        const eid = mentionByEntity[s.mention.mention_id];
        return (
          <mark key={i} className={eid === selected ? "sel" : ""}
                onClick={() => onSelectMention(eid)}
                title={s.mention.surface + " · " + labelForType(entityById[eid]?.type)}>
            {s.text}
          </mark>
        );
      })}
    </div>
  );
});
