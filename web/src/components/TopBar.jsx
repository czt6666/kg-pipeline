// Nav mirrors the actual pipeline order (stage0 OCR -> stage1 extract -> stage3 align ->
// stage7 merge -> retrieval/QA -> eval), not an arbitrary feature list, so the top bar
// itself documents "what stage does this page correspond to." Stages without a shipped
// page yet (align/retrieval/qa) still get a slot + route so the pipeline shape is visible
// end-to-end; they render a "soon" page instead of disappearing.
export const PIPELINE_STAGES = [
  { key: "ocr", route: "ocr", label: "OCR原文" },
  { key: "preprocess", route: "preprocess", label: "文本预处理" },
  { key: "debug", route: "debug", label: "三元组提取" },
  { key: "align", route: "align", label: "实体对齐", soon: true },
  { key: "graph", route: "graph", label: "完整知识图谱" },
  { key: "retrieval", route: "retrieval", label: "检索" },
  { key: "qa", route: "qa", label: "问答" },
  { key: "benchmark", route: "benchmark", label: "测评", soon: true },
];

export function TopBar({ route }) {
  return (
    <header className="topbar">
      <a href="#/" className="brand">◆ KG 工作台</a>
      <nav className="pipeline-nav">
        {PIPELINE_STAGES.map((s, i) => (
          <span className="pipeline-step" key={s.key}>
            {i > 0 && <span className="pipeline-arrow">›</span>}
            <a
              href={`#/${s.route}`}
              className={(route === s.route ? "on" : "") + (s.soon ? " soon" : "")}
            >
              <span className="step-no">{i + 1}</span>
              {s.label}
              {s.soon && <span className="soon-badge">待实现</span>}
            </a>
          </span>
        ))}
      </nav>
      <div className="spacer" />
    </header>
  );
}
