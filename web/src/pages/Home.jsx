import { useEffect, useState } from "react";
import { TopBar } from "../components/TopBar.jsx";
import { StatTile } from "../components/StatTile.jsx";
import { getJSON, go } from "../utils/api.js";

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
          <p className="lead">从原始文本自动抽取实体与关系，跨文档对齐合并为完整知识图谱，并提供语义检索、来源溯源与逐文档调试能力。</p>
        </div>
        <div className="stats-row center">
          <StatTile label="数据集" value={merged.length || "—"} />
          <StatTile label="实体总数" value={totals.nodes.toLocaleString()} />
          <StatTile label="关系总数" value={totals.edges.toLocaleString()} />
          <StatTile label="源文档总数" value={totals.docs.toLocaleString()} />
        </div>
        <div className="cards">
          <div className="card" onClick={() => go("graph")}>
            <div className="card-icon">🕸️</div>
            <h2>完整知识图谱</h2>
            <p>同一数据集下所有文档跨文档对齐、合并成一张图。从连接数最高的核心实体或语义检索入手，展开任意实体的局部关系网络，并查看它出现在哪些原文中。</p>
            <div className="tags">{merged.map(m => <span key={m.dataset}><b>{m.dataset}</b> {m.n_nodes} 实体</span>)}</div>
            <span className="go">进入 →</span>
          </div>
          <div className="card" onClick={() => go("debug")}>
            <div className="card-icon">🔬</div>
            <h2>细节调试</h2>
            <p>按数据集与切分逐篇查看：原文中的实体高亮标注、该篇文档的局部知识图谱，以及语义 / 词法 / 图检索三种召回方式的对照结果。用于排查抽取与对齐质量。</p>
            <div className="tags">逐文档 · 逐切分 · 三路检索对照</div>
            <span className="go">进入 →</span>
          </div>
        </div>
      </div>
    </>
  );
}
