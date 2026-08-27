import { colorForType } from "../utils/types.js";

export function TypeBarChart({ counts, active, onPick }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const max = entries.length ? entries[0][1] : 1;
  return (
    <div className="bar-chart">
      {entries.map(([t, c]) => (
        <div key={t} className={"bar-row" + (active === t ? " active" : "")} onClick={() => onPick(t)}>
          <span className="bar-label" style={{ color: colorForType(t) }}>{t}</span>
          <span className="bar-track"><span className="bar-fill" style={{ width:(c/max*100)+"%", background: colorForType(t) }} /></span>
          <span className="cnt">{c}</span>
        </div>
      ))}
    </div>
  );
}
