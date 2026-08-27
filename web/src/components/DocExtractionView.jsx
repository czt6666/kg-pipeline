import { useMemo } from "react";
import { GraphCanvas } from "./GraphCanvas.jsx";
import { labelForType } from "../utils/types.js";

export function DocExtractionView({ doc, matchNames }) {
  const mentionByEntity = useMemo(() => {
    const m = {};
    for (const n of doc.nodes) for (const mid of n.mention_ids || []) m[mid] = n.entity_id;
    return m;
  }, [doc]);
  const entityById = useMemo(() => Object.fromEntries(doc.nodes.map(n => [n.entity_id, n])), [doc]);
  const matchSet = useMemo(() => new Set((matchNames || []).map(s => s.toLowerCase())), [matchNames]);
  const focusLocalId = useMemo(() => {
    const hit = doc.nodes.find(n => matchSet.has(n.name.toLowerCase()) || (n.aliases || []).some(a => matchSet.has(a.toLowerCase())));
    return hit ? hit.entity_id : null;
  }, [doc, matchSet]);

  const spans = useMemo(() => {
    const ms = [...doc.mentions].filter(m => m.char_start != null && m.char_end != null).sort((a, b) => a.char_start - b.char_start);
    const out = [];
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

  return (
    <div className="modal-body">
      <div className="text-view">
        {spans.map((s, i) => {
          if (!s.mention) return <span key={i}>{s.text}</span>;
          const eid = mentionByEntity[s.mention.mention_id];
          const isMatch = matchSet.has((s.mention.surface || "").toLowerCase());
          return (
            <mark key={i} className={isMatch ? "sel" : ""}
                  title={s.mention.surface + " · " + labelForType(entityById[eid]?.type)}>
              {s.text}
            </mark>
          );
        })}
      </div>
      <div className="modal-graph">
        <GraphCanvas nodes={doc.nodes} edges={doc.edges} onSelectNode={() => {}} centerId={focusLocalId} />
      </div>
    </div>
  );
}
