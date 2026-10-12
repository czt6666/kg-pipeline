import { useEffect, useMemo, useState } from "react";
import { TopBar } from "../components/TopBar.jsx";
import { StatTile } from "../components/StatTile.jsx";
import { getJSON } from "../utils/api.js";

const RUN_NOTES = {
  v0: "初始基线，未改图谱",
  v1_boundaryfix: "修复分段边界 bug（当前最优）",
  v2_retrybudget: "修复截断丢内容，内容审核通过但分数降了",
  v3_zhengsuffix: "证候命名去重，内容审核通过但分数降了",
  v4_surgical: "最小范围精确修复，仍然降分",
};

function pct(x) { return (x * 100).toFixed(1) + "%"; }

/* Horizontal bar comparing every eval run's overall hit rate, so the up-then-down-x3
   pattern from the round loop (see versions.md) is visible at a glance rather than
   read out of a table. */
function RunComparisonChart({ runs, selected, onPick }) {
  const max = Math.max(0.01, ...runs.map(r => r.hit_rate));
  return (
    <div className="bar-chart">
      {runs.map(r => (
        <div key={r.name} className={"bar-row run-row" + (selected === r.name ? " active" : "")} onClick={() => onPick(r.name)}>
          <span className="bar-label">{r.name}</span>
          <span className="bar-track"><span className="bar-fill" style={{ width: (r.hit_rate / max * 100) + "%", background: r.name === "v1_boundaryfix" ? "var(--good)" : "var(--accent)" }} /></span>
          <span className="cnt">{pct(r.hit_rate)}</span>
        </div>
      ))}
    </div>
  );
}

function TypeBreakdown({ byType, active, onPick }) {
  const entries = Object.entries(byType);
  return (
    <div className="bar-chart">
      {entries.map(([t, s]) => (
        <div key={t} className={"bar-row type-row" + (active === t ? " active" : "")} onClick={() => onPick(t === active ? null : t)}>
          <span className="bar-label">{t}</span>
          <span className="bar-track"><span className="bar-fill" style={{ width: (s.rate * 100) + "%" }} /></span>
          <span className="cnt">{s.hits}/{s.n}</span>
        </div>
      ))}
    </div>
  );
}

function PromptModal({ name, onClose }) {
  const [content, setContent] = useState(null);
  useEffect(() => { getJSON(`/api/prompts/${name}`).then(d => setContent(d.content)); }, [name]);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <span className="modal-title">抽取 Prompt · {name}</span>
          <span className="muted">这是实际发给模型的完整 prompt（schema + few-shot 全部渲染在内），改图谱前后用的是同一份</span>
          <div className="spacer" />
          <button onClick={onClose}>关闭</button>
        </div>
        <div className="modal-body" style={{ gridTemplateColumns: "1fr" }}>
          <pre className="prompt-view">{content ?? "加载中…"}</pre>
        </div>
      </div>
    </div>
  );
}

function QuestionRow({ q }) {
  const answerText = Array.isArray(q.answer) ? q.answer.join("、") : q.answer;
  const retrievedSet = new Set((q.retrieved || []).map(s => s.replace(/证$/, "")));
  return (
    <div className={"qrow-card" + (q.hit ? " hit" : " miss")}>
      <div className="qrow-head">
        <span className={"hit-badge" + (q.hit ? " hit" : " miss")}>{q.hit ? "命中" : "未命中"}</span>
        <span className="chip">{q.type}</span>
        <span className="muted">{q.id}</span>
      </div>
      <div className="qrow-q">{q.question}</div>
      <div className="row"><span className="k">标准答案</span>{answerText}</div>
      <div className="row">
        <span className="k">检索 top5</span>
        {(q.retrieved || []).map((r, i) => (
          <span key={i} className="chip" style={{ marginRight: 4, background: retrievedSet.has(r.replace(/证$/, "")) && !q.hit ? "var(--surface-2)" : undefined }}>{r}</span>
        ))}
      </div>
      {q.evidence && (
        <div className="row evidence">
          <span className="k">原文出处</span>
          {Array.isArray(q.evidence.doc_id) ? q.evidence.doc_id.join(", ") : q.evidence.doc_id}
          {q.evidence.page && <> · 第 {Array.isArray(q.evidence.page) ? q.evidence.page.join("/") : q.evidence.page} 页</>}
          {q.evidence.quote && <div className="quote">"{q.evidence.quote}"</div>}
        </div>
      )}
    </div>
  );
}

/* ---------- 评测集 Benchmark ---------- */
export function Benchmark() {
  const [runs, setRuns] = useState([]);
  const [runName, setRunName] = useState("v1_boundaryfix");
  const [questions, setQuestions] = useState([]);
  const [typeFilter, setTypeFilter] = useState(null);
  const [hitFilter, setHitFilter] = useState("all");
  const [showPrompt, setShowPrompt] = useState(false);

  useEffect(() => {
    getJSON("/api/eval/runs").then(rs => {
      setRuns(rs);
      if (rs.length && !rs.some(r => r.name === "v1_boundaryfix")) setRunName(rs[0].name);
    });
  }, []);

  useEffect(() => {
    if (!runName) return;
    getJSON(`/api/eval/run/${runName}`).then(setQuestions);
  }, [runName]);

  const current = runs.find(r => r.name === runName);

  const filtered = useMemo(() => {
    return questions.filter(q => {
      if (typeFilter && q.type !== typeFilter) return false;
      if (hitFilter === "hit" && !q.hit) return false;
      if (hitFilter === "miss" && q.hit) return false;
      return true;
    });
  }, [questions, typeFilter, hitFilter]);

  return (
    <>
      <TopBar route="benchmark" />
      <div className="bench">
        <div className="bench-top">
          <label className="muted">评测版本
            <select value={runName} onChange={e => setRunName(e.target.value)} style={{ marginLeft: 6, minWidth: 200 }}>
              {runs.map(r => <option key={r.name} value={r.name}>{r.name}（{pct(r.hit_rate)}）</option>)}
            </select>
          </label>
          {current && <span className="muted">{RUN_NOTES[current.name] || ""}</span>}
          <div className="spacer" />
          <button onClick={() => setShowPrompt(true)}>查看抽取 Prompt</button>
        </div>

        <div className="bench-body">
          <div className="rail">
            {current && (
              <div className="stats-row">
                <StatTile label="命中率" value={pct(current.hit_rate)} sub={`${current.hits}/${current.n} 题`} />
              </div>
            )}
            <div>
              <h3>各版本对比（100 题 top5 命中率）</h3>
              <RunComparisonChart runs={runs} selected={runName} onPick={setRunName} />
            </div>
            {current && (
              <div>
                <div className="rail-row-head"><h3>本版本分类命中率</h3>{typeFilter && <button className="link" onClick={() => setTypeFilter(null)}>清除筛选</button>}</div>
                <TypeBreakdown byType={current.by_type} active={typeFilter} onPick={setTypeFilter} />
              </div>
            )}
            <div>
              <h3>题目筛选</h3>
              <div className="seg">
                <button className={"seg-btn" + (hitFilter === "all" ? " on" : "")} onClick={() => setHitFilter("all")}>全部</button>
                <button className={"seg-btn" + (hitFilter === "hit" ? " on" : "")} onClick={() => setHitFilter("hit")}>命中</button>
                <button className={"seg-btn" + (hitFilter === "miss" ? " on" : "")} onClick={() => setHitFilter("miss")}>未命中</button>
              </div>
              <p className="hint" style={{ marginTop: 10 }}>共 {filtered.length} / {questions.length} 题{typeFilter ? `（分类：${typeFilter}）` : ""}</p>
            </div>
          </div>

          <div className="qlist">
            {filtered.map(q => <QuestionRow key={q.id} q={q} />)}
            {filtered.length === 0 && <div className="empty">没有符合筛选条件的题目</div>}
          </div>
        </div>
      </div>
      {showPrompt && <PromptModal name="extraction/tcm:template" onClose={() => setShowPrompt(false)} />}
    </>
  );
}
