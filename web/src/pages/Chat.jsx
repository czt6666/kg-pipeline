import { useEffect, useMemo, useRef, useState } from "react";
import { TopBar } from "../components/TopBar.jsx";
import { Markdown } from "../components/Markdown.jsx";
import { getJSON, postJSON } from "../utils/api.js";
import { mergeKey, mergeLabel } from "../utils/merged.js";

/* 问答：TCM 智慧诊疗 Agent Loop 的对话界面。前端无状态——每轮把完整消息历史 POST 给
   /api/kg/agent/chat，KG 服务跑一轮单控制器 ReAct 循环（控制器每步决定 检索/追问/回答/转诊，
   检索结果喂回继续，可多轮下钻）返回 {action, reply, candidates, evidence, trace}。后端现在
   始终带 trace（不再需要 debug 开关才请求），前端把每一步渲染成一条 markdown 格式的推理
   时间线，默认展开——"检索过程对用户可见"是硬要求，不是可选的调试功能。 */

const ACTION_META = {
  ANSWER:   { label: "回答",   cls: "act-answer" },
  ASK:      { label: "追问",   cls: "act-ask" },
  RETRIEVE: { label: "检索",   cls: "act-retrieve" },
  TRIAGE:   { label: "分诊",   cls: "act-triage" },
  ESCALATE: { label: "建议就医", cls: "act-escalate" },
};

const SUGGESTIONS = [
  "我失眠",
  "我感冒了",
  "柴胡的功效是什么？",
  "我这段时间皮肤和眼睛发黄、颜色发暗，胃口差、大便稀溏、很疲乏",
];

// controller 决策里 action 是小写的 retrieve/ask/answer/escalate（跟终止动作的大写
// Action 枚举是两套不同的值域，分别对应"这一步决定做什么"和"这一轮最终以什么收尾"）。
const STEP_META = {
  controller:        { icon: "🧭", label: "决策" },
  retrieval_result:  { icon: "🔎", label: "检索" },
  retrieval_skipped: { icon: "🔎", label: "检索" },
  answer:            { icon: "✍️", label: "生成回答" },
  escalate:          { icon: "⚠️", label: "转诊建议" },
};
const DECISION_LABEL = { retrieve: "检索", ask: "追问", answer: "回答", escalate: "转诊" };

// 把一步 trace 的结构化 output 转成一段 markdown -- 不直接 JSON.stringify，用户看的是
// "这一步在想什么/查了什么"，不是原始数据结构。
function stepMarkdown(step) {
  const o = step.output || {};
  switch (step.stage) {
    case "controller": {
      const lines = [`**决定：${DECISION_LABEL[o.action] || o.action}**`];
      if (o.rationale) lines.push(`> ${o.rationale}`);
      if (o.action === "retrieve" && o.queries?.length) {
        lines.push("", "本步检索目标：");
        for (const q of o.queries) {
          const bits = [q.type, q.focus].filter(Boolean).join(" · ");
          lines.push(`- \`${q.term}\`${bits ? `（${bits}）` : ""}`);
        }
      }
      if (o.action === "ask" && o.question) {
        lines.push("", `**追问**：${o.question}`);
      }
      if (o.candidates?.length) {
        lines.push("", "候选证候：" + o.candidates.map(c => `**${c.syndrome || c.name}**${c.note ? `（${c.note}）` : ""}`).join("、"));
      }
      if (o.capped) {
        lines.push("", `_预算已用尽，已强制改为${DECISION_LABEL[o.capped.includes("ask") ? "ask" : "retrieve"] || "回答"}_`);
      }
      return lines.join("\n");
    }
    case "retrieval_result": {
      const lines = ["**检索结果**"];
      for (const e of o.evidence || []) {
        if (!e.found) {
          lines.push(`- \`${e.query}\` → 未命中`);
          continue;
        }
        const head = e.resolved_entity || {};
        lines.push(`- \`${e.query}\` → **${head.name}**（${head.type}）`);
        const facts = (e.facts || []).slice(0, 5);
        for (const f of facts) lines.push(`  - ${f.sentence}`);
        if ((e.facts || []).length > facts.length) lines.push(`  - _（还有 ${e.facts.length - facts.length} 条）_`);
      }
      return lines.join("\n");
    }
    case "retrieval_skipped":
      return `**跳过检索**：${o.reason || "没有有效的检索目标"}`;
    case "answer":
      return "**生成回答**：根据以上对话与检索到的证据组织最终回复。";
    case "escalate":
      return "**转诊建议**：识别到较高风险或需线下处置的信号，直接给出就医建议，不再检索或追问。";
    default:
      return `\`\`\`json\n${JSON.stringify(o, null, 2)}\n\`\`\``;
  }
}

// 推理时间线：每条助手消息下方常驻展示，默认展开——检索/决策过程对用户可见是硬要求。
function ReasoningView({ trace }) {
  const [open, setOpen] = useState(true);
  if (!trace || !trace.length) return null;
  return (
    <div className="reasoning">
      <button className="reasoning-head" onClick={() => setOpen(o => !o)}>
        <span className="reasoning-title">{open ? "▾" : "▸"} 推理过程（{trace.length} 步）</span>
      </button>
      {open && (
        <div className="reasoning-body">
          {trace.map(s => {
            const meta = STEP_META[s.stage] || { icon: "•", label: s.stage };
            return (
              <div className="reasoning-step" key={s.step}>
                <div className="reasoning-step-head">
                  <span>{meta.icon} {meta.label}</span>
                  {s.meta?.latency_ms != null && <span className="reasoning-step-latency">{s.meta.latency_ms}ms</span>}
                </div>
                <Markdown>{stepMarkdown(s)}</Markdown>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function Chat() {
  const [mergedList, setMergedList] = useState([]);
  const [selectedKey, setSelectedKey] = useState(null);
  // messages: [{role, content, action?, trace?, candidates?, error?}] — role/content 发给
  // 后端，其余仅前端展示。
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    getJSON("/api/kg/merged").then(list => {
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
      const r = await postJSON("/api/kg/agent/chat", {
        messages: [...history, { role: "user", content: q }],
        dataset: selected.dataset,
        merge: selected.merge,
      });
      setMessages(m => [...m, { role: "assistant", content: r.reply, action: r.action,
                                candidates: r.candidates, trace: r.trace }]);
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
          <button className="link" onClick={reset} disabled={!messages.length}>清空对话</button>
          <span className="spacer" />
          <span className="hint">TCM 智慧诊疗助手 · 中医知识科普，非线下诊疗依据 · 每条回复都附完整推理过程</span>
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
                    <div className={"bubble" + (m.error ? " error" : "")}>
                      {m.role === "assistant" && !m.error ? <Markdown>{m.content}</Markdown> : m.content}
                    </div>
                    {m.role === "assistant" && m.candidates?.length > 0 && (
                      <div className="cand-row">
                        <span className="cand-label">候选证候</span>
                        {m.candidates.map((c, i) => (
                          <span className="chip" key={i} title={c.note || ""}>{c.syndrome || c.name || "?"}</span>
                        ))}
                      </div>
                    )}
                    {m.role === "assistant" && <ReasoningView trace={m.trace} />}
                  </div>
                </div>
              ))
            )}
            {busy && (
              <div className="msg assistant">
                <div className="msg-avatar">医</div>
                <div className="msg-main">
                  <div className="bubble"><span className="loading-row"><span className="spinner" />检索知识图谱、推理中…</span></div>
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
