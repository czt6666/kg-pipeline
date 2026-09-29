import { useEffect, useState } from "react";
import { hashRoute } from "./utils/api.js";
import { Home } from "./pages/Home.jsx";
import { OcrView } from "./pages/OcrView.jsx";
import { Preprocess } from "./pages/Preprocess.jsx";
import { GraphExplorer } from "./pages/GraphExplorer.jsx";
import { DebugView } from "./pages/DebugView.jsx";
import { Retrieval } from "./pages/Retrieval.jsx";
import { Chat } from "./pages/Chat.jsx";
import { ComingSoon } from "./pages/ComingSoon.jsx";

export function App() {
  const [route, setRoute] = useState(hashRoute());
  useEffect(() => {
    const onHash = () => setRoute(hashRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  if (route === "ocr") return <OcrView />;
  if (route === "preprocess") return <Preprocess />;
  if (route === "debug") return <DebugView />;
  if (route === "align") return (
    <ComingSoon route="align" icon="🔗" title="实体对齐"
      description="跨文档同名/同义实体的对齐结果查看页面，对应 stage3 的输出（alignment_map.jsonl）。当前对齐结果已经在“完整知识图谱”里合并展示，独立的对齐审阅页面尚未实现。" />
  );
  if (route === "graph") return <GraphExplorer />;
  if (route === "retrieval") return <Retrieval />;
  if (route === "qa") return <Chat />;
  if (route === "benchmark") return (
    <ComingSoon route="benchmark" icon="📊" title="测评"
      description="100 题评测集的问题库（eval/questions.jsonl）已经在，但各版本的评测结果文件（eval/baseline_results_*.jsonl）当前不在仓库里，页面拿不到数据会直接报错，所以先收回成“待实现”，等重新跑一遍评测再打开。" />
  );
  return <Home />;
}
