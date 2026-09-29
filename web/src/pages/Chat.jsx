import { useEffect, useMemo, useRef, useState } from "react";
import { TopBar } from "../components/TopBar.jsx";
import { getJSON, postJSON } from "../utils/api.js";
import { mergeKey, mergeLabel } from "../utils/merged.js";

/* 问答：TCM 智慧诊疗 Agent Loop 的对话界面。前端无状态——每轮把完整消息历史 POST 给
   /api/agent/chat，后端跑一轮 Agent Loop（理解→风险→决策→检索→判断→回答/追问/分诊/转诊）
   返回 {action, reply, trace?}。debug 开关打开时展示每轮的分阶段推理 trace（仅调试用，正式
   回答里不含任何内部信息）。 */

// 终止动作 -> 展示用的中文标签 + 颜色语义（沿用全局设计 token）。
const ACTION_META = {
  ANSWER:   { label: "回答",   cls: "act-answer" },
  ASK:      { label: "追问",   cls: "act-ask" },
  RETRIEVE: { label: "检索",   cls: "act-retrieve" },
  TRIAGE:   { label: "分诊",   cls: "act-triage" },
  ESCALATE: { label: "建议就医", cls: "act-escalate" },
};

const SUGGESTIONS = [
  "柴胡的功效是什么？",
  "消渴一般分为哪些证型？",
  "我最近老是失眠，晚上心烦、口干",
  "这两天头晕、耳鸣，还有点腰膝酸软",
];

// 始终展示的「检索依据」：这一轮从知识图谱查到了什么（命中实体 + 事实），以及归纳出的候选证候。
// 让检索过程对用户可见，是这个界面的硬要求。
function EvidenceView({ evidence, candidates }) {
  const [open, setOpen] = useState(false);
  const hits = (evidence || []).filter(e => e.found);
  if (!hits.length && !(candidates || []).length) return null;
  const factCount = hits.reduce((n, e) => n + (e.facts?.length || 0), 0);
  return (
    <div className="evid">
      {(candidates || []).length > 0 && (
        <div className="evid-cands">
          <span className="evid-cands-label">候选证候</span>
          {candidates.map((c, i) => <span className="chip" key={i}>{c.syndrome || c.name || "?"}</span>)}
        </div>
      )}
      {hits.length > 0 && (
        <>
          <button className="link" onClick={() => setOpen(o => !o)}>
            {open ? "▾ 收起检索依据" : `▸ 检索依据（${hits.length} 个词条 / ${factCount} 条事实）`}
          </button>
          {open && (
            <div className="evid-body">
              {hits.map((e, i) => (
                <div className="evid-item" key={i}>
                  <div className="evid-head">检索「{e.query}」→ <b>{e.entity}</b>（{e.type}）</div>
                  <ul>{(e.facts || []).map((f, j) => <li key={j}>{f}</li>)}</ul>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function TraceView({ trace }) {
  const [open, setOpen] = useState(false);
  if (!trace || !trace.length) return null;
  return (
    <div className="trace">
      <button className="link" onClick={() => setOpen(o => !o)}>
        {open ? "▾ 收起推理过程" : `▸ 查看推理过程（${trace.length} 步）`}
      </button>
      {open && (
        <div className="trace-body">
          {trace.map(s => (
            <div className="trace-step" key={s.step}>
              <div className="trace-head">
                <span className="trace-stage">{s.stage}</span>
                {s.meta?.latency_ms != null && <span className="muted">{s.meta.latency_ms}ms</span>}
              </div>
              <pre className="trace-out">{JSON.stringify(s.output, null, 2)}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Chat() {
  const [mergedList, setMergedList] = useState([]);
  const [selectedKey, setSelectedKey] = useState(null);
  const [maxRounds, setMaxRounds] = useState(3);
  const [debug, setDebug] = useState(false);
  // messages: [{role, content, action?, trace?, error?}] — role/content 发给后端，其余仅前端展示。
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    getJSON("/api/merged").then(list => {
      setMergedList(list);
      if (!list.length) return;
      // 默认选合并的三本书全量图（覆盖面最广），没有就退回第一个。
      const combined = list.find(m => (m.merge || "").includes("tcm_all"));
      setSelectedKey(mergeKey(combined || list[0]));
    });
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy]);

  const selected = useMemo(() => mergedList.find(m => mergeKey(m) === selectedKey) || null, [mergedList, selectedKey]);

  const send = async (text) => {
    const q = (text ?? input).trim();
    if (!q || busy || !selected) return;
    const history = messages.map(m => ({ role: m.role, content: m.content }));
    const next = [...messages, { role: "user", content: q }];
    setMessages(next);
    setInput("");
    setBusy(true);
    try {
      const r = await postJSON("/api/agent/chat", {
        messages: [...history, { role: "user", content: q }],
        dataset: selected.dataset,
        merge: selected.merge,
        max_rounds: maxRounds,
        debug,
      });
      setMessages(m => [...m, { role: "assistant", content: r.reply, action: r.action,
                                evidence: r.evidence, candidates: r.candidates, trace: r.trace }]);
    } catch (e) {
      setMessages(m => [...m, { role: "assistant", content: `抱歉，出错了：${e.message}`, error: true }]);
    } finally {
      setBusy(false);
    }
  };

  const reset = () => { setMessages([]); setInput(""); };

  return (
    <>
      <TopBar route="qa" />
      <div className="explorer">
        <div className="explorer-top">
          <select className="dataset-select" value={selectedKey || ""} onChange={e => setSelectedKey(e.target.value)}>
            {mergedList.map(m => <option key={mergeKey(m)} value={mergeKey(m)}>{mergeLabel(m)}</option>)}
          </select>
          <label className="chat-ctl" title="一次咨询里最多追问几次（超过就直接给方向）">
            追问上限
            <select value={maxRounds} onChange={e => setMaxRounds(Number(e.target.value))}>
              {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label className="chat-ctl" title="显示每轮 Agent 的分阶段推理过程（仅调试）">
            <input type="checkbox" checked={debug} onChange={e => setDebug(e.target.checked)} />
            推理过程
          </label>
          <button className="link" onClick={reset} disabled={!messages.length}>清空对话</button>
          <span className="hint">TCM 智慧诊疗助手 · 中医知识科普，非线下诊疗依据。</span>
        </div>

        <div className="chat-wrap">
          <div className="chat-scroll" ref={scrollRef}>
            {messages.length === 0 ? (
              <div className="chat-empty">
                <div className="card-icon">💬</div>
                <h2>问我一个中医问题</h2>
                <p className="hint">基于教材知识图谱检索作答；描述症状时会先做风险判断与初步分诊。</p>
                <div className="chat-suggests">
                  {SUGGESTIONS.map(s => (
                    <button key={s} className="chip clickable" onClick={() => send(s)}>{s}</button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m, i) => (
                <div className={"msg " + m.role} key={i}>
                  <div className="msg-avatar">{m.role === "user" ? "你" : "医"}</div>
                  <div className="msg-main">
                    {m.role === "assistant" && m.action && ACTION_META[m.action] && (
                      <span className={"act-badge " + ACTION_META[m.action].cls}>{ACTION_META[m.action].label}</span>
                    )}
                    <div className={"bubble" + (m.error ? " error" : "")}>{m.content}</div>
                    {m.role === "assistant" && <EvidenceView evidence={m.evidence} candidates={m.candidates} />}
                    {m.role === "assistant" && <TraceView trace={m.trace} />}
                  </div>
                </div>
              ))
            )}
            {busy && (
              <div className="msg assistant">
                <div className="msg-avatar">医</div>
                <div className="msg-main">
                  <div className="bubble"><span className="loading-row"><span className="spinner" />思考中…</span></div>
                </div>
              </div>
            )}
          </div>

          <div className="chat-composer">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="输入你的问题，Enter 发送，Shift+Enter 换行"
              rows={1}
              disabled={busy}
              onKeyDown={e => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
              }}
            />
            <button className="primary" onClick={() => send()} disabled={busy || !input.trim() || !selected}>
              {busy ? "…" : "发送"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
