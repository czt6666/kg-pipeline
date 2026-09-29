import { useEffect, useState } from "react";
import { TopBar } from "../components/TopBar.jsx";
import { StatTile } from "../components/StatTile.jsx";
import { getJSON, go } from "../utils/api.js";
import { mergeKey, mergeLabel } from "../utils/merged.js";

// One card per pipeline stage, in pipeline order (mirrors TopBar's PIPELINE_STAGES) —
// the homepage doubles as a map of the whole pipeline, not just a features list, so
// "not implemented yet" stages stay visible here instead of being hidden.
const STAGES = [
  { route: "ocr", icon: "📄", title: "OCR 原文", tags: "逐页原文 · stage0",
    desc: "按数据集与切分逐页查看扫描版原文的 OCR 识别结果，是整条流水线最原始的输入。" },
  { route: "preprocess", icon: "🧹", title: "文本预处理", tags: "段落级对照 · 指代消解 · 复核队列",
    desc: "三元组抽取前的文本预处理层：原文 → 字符级规范化 → 古文白话化/简单句拆分/指代还原。逐段对照原文与拆分结果，标出需要人工复核的段落。" },
  { route: "debug", icon: "🔬", title: "三元组提取", tags: "逐文档 · 逐切分 · 三路检索对照",
    desc: "按数据集与切分逐篇查看：原文中的实体高亮标注、该篇文档的局部知识图谱，以及语义/词法/图检索三种召回方式的对照结果。用于排查抽取质量。" },
  { route: "align", icon: "🔗", title: "实体对齐", tags: "待实现", soon: true,
    desc: "跨文档同名/同义实体对齐（stage3）结果的独立审阅页面，目前对齐结果已并入下一步的完整知识图谱。" },
  { route: "graph", icon: "🕸️", title: "完整知识图谱", tags: null,
    desc: "同一数据集下所有文档跨文档对齐、合并成一张图。从连接数最高的核心实体或语义检索入手，展开任意实体的局部关系网络，并查看它出现在哪些原文中。" },
  { route: "retrieval", icon: "🔍", title: "检索", tags: "待实现", soon: true,
    desc: "面向完整知识图谱的独立检索入口，尚未实现——目前检索能力只在“三元组提取”页作为调试面板存在。" },
  { route: "qa", icon: "💬", title: "问答", tags: "待实现", soon: true,
    desc: "基于知识图谱的检索增强问答，尚未实现。" },
  { route: "benchmark", icon: "📊", title: "测评", tags: "待实现", soon: true,
    desc: "100 题评测集已就绪，但各版本的评测结果文件当前缺失，页面暂时收回为待实现，等重新跑一遍评测再打开。" },
];

export function Home() {
  const [merged, setMerged] = useState([]);
  useEffect(() => { getJSON("/api/merged").then(setMerged); }, []);
  const totals = merged.reduce((a, m) => ({
    nodes: a.nodes + (m.n_nodes||0), edges: a.edges + (m.n_edges||0), docs: a.docs + (m.n_docs||0),
  }), { nodes:0, edges:0, docs:0 });

  return (
    <>
      <TopBar route="home" />
      <div className="home">
        <div className="hero">
          <h1>知识图谱构建 &amp; 检索工作台</h1>
          <p className="lead">从原始扫描件 OCR 开始，经文本预处理、三元组抽取、实体对齐，合并为完整知识图谱，并提供检索、问答与评测——下面按流水线顺序排列。</p>
        </div>
        <div className="stats-row center">
          <StatTile label="知识图谱" value={merged.length || "—"} />
          <StatTile label="实体总数" value={totals.nodes.toLocaleString()} />
          <StatTile label="关系总数" value={totals.edges.toLocaleString()} />
          <StatTile label="源文档总数" value={totals.docs.toLocaleString()} />
        </div>
        <div className="cards">
          {STAGES.map((s, i) => (
            <div key={s.route} className={"card" + (s.soon ? " card-soon" : "")} onClick={() => go(s.route)}>
              <div className="card-icon">{s.icon}</div>
              <h2><span className="step-no">{i + 1}</span> {s.title}</h2>
              <p>{s.desc}</p>
              <div className="tags">
                {s.route === "graph"
                  ? merged.map(m => <span key={mergeKey(m)}><b>{mergeLabel(m)}</b> {m.n_nodes} 实体</span>)
                  : s.tags && <span>{s.tags}</span>}
              </div>
              <span className="go">{s.soon ? "查看说明 →" : "进入 →"}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
