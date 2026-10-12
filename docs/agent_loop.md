# TCM 智慧诊疗 Agent Loop（单控制器 ReAct 版）

一个**单控制器的 ReAct 循环**（借鉴 Claude Code 的「一个大脑 + 工具」架构）：每一步由同一个
控制器 LLM 读 {对话 + 图谱本体 + 已检索证据 + 预算} 决定下一步动作，检索是它调用的工具，结果立刻
喂回去让它继续决定——于是它能在一轮对话里**多轮检索、逐层下钻**（病 → 证候 → 方剂/中药）再作答。

代码在 `assistant/`；交互调试 `src/agent_cli.py`；场景回归 `scripts/agent_scenarios.py`；
HTTP 入口 `POST /api/kg/agent/chat`；前端问答页 `web/src/pages/Chat.jsx`（`#/qa`）。

## 为什么是这个形状（相对上一版）

上一版是固定流水线：interpret → risk → differential → 路由，每轮 3-4 次独立 LLM 调用。它
（1）会循环提问（看不到自己问过什么、证据也常为空）；（2）无法多轮检索（检索路径写死）；
（3）环节多、难维护。本版按第一性原理重构——**看病的本质就是「查资料 → 判断 → 再查/追问/作答」
的一个循环**，所以只保留一个会用工具的大脑：

| 上一版的问题 | 本版怎么一并解决 |
|---|---|
| 循环提问 / 目标丢失 | 控制器每步都看**完整对话**（含它自己问过的话和用户的回答）+ 已问次数，并被明确要求「不得重复问」；预算耗尽硬性转 answer |
| 思考臃肿、调用多 | 从 6 个 stage prompt 砍到 **2 种**：控制器（决策）+ 作答/转诊（成文）；风险判断并入控制器 |
| 不能多轮检索 | 循环在一轮内反复调用控制器，看到第一轮证据后可再发第二轮查询（感冒→证候→方剂） |
| 不懂图谱结构 | 把 `schema.vocabulary_block()`（实体类型 + 关系 domain→range + 常用检索路径）注入控制器上下文 |

还有一个**根因级修复**：合并图数据实际在 `data/work/TCM/`，而 `graph_dir` 读 `data/graph/TCM/`，
导致**检索一直返回空**（agent 当然「根本不能用」、且因为没有证据而不停追问）。已把 `data/work` 下的
`merged_*` 软链到 `data/graph/TCM/`、splits 软链到 `data/pipeline/TCM/splits/`。

## 流程

```
用户消息 → new_turn（清空本轮证据）
  循环，最多 max_steps 步：
    decide = controller(对话 + 本体 + 已检索证据 + 预算)   # 一次 LLM 调用
      retrieve  → 执行查询，证据追加，回到循环（多轮检索就发生在这里）
      ask       → 返回这一个「剪枝问题」（本轮结束；预算用尽则被强制转 answer）
      answer    → 用已收集证据成文作答（本轮结束）
      escalate  → 急危重/需线下，安全转诊（本轮结束）
  （步数用尽仍未终止 → 用现有证据作答，兜底）
```

诊疗三步走（写在控制器 prompt 里）：① 查主诉对应的疾病/症状，拿候选**证候**；② 查选定证候，拿
**治法/方剂/常用药**；③ 要具体药物组成再查**方剂**。缺哪步查哪步。

**关键点：控制器只负责「说出要查哪个实体名」，关系由图谱给**——所以它结构上无法发明 schema
里不存在的关系/类型（上一版让 LLM 生成 schema path 的负担没有了）。query 的 `focus` 仅用于把命中
实体的相关事实排到前面。

## 模块（都可单独替换 / 测试）

| 文件 | 职责 |
|---|---|
| `schema_spec.py` | 合法实体/关系 + `vocabulary_block()`（注入控制器的本体知识）；`validate_path` 仍供校验/测试 |
| `state.py` | `AgentState`：对话、`understanding`(最近一次控制器决策)、`candidates`、`evidence`、`ask_rounds`/`max_ask_rounds`、`retrieval_rounds`/`max_retrieval_rounds`、`trace`；`to_dict()` 可复盘 |
| `actions.py` | Action 枚举、`RetrievalRequest`/`RetrievalQuery`/`Evidence` |
| `reasoner.py` | LLM 边界：`think()`(JSON+一次修复)/`write()`(正文)；`ScriptedReasoner` 供测试 |
| `retrieval_adapter.py` | 查询→`hybrid_search`→归一 `Evidence`，按 focus 关系排序；`FakeRetrievalAdapter` 供测试 |
| `prompts.py` | 两种 prompt：`controller_prompt`（大脑）、`answer_prompt`/`escalate_prompt`（成文）|
| `stages.py` | `decide`（控制器 + 解析 + 硬上限）/`run_retrieval`（去重+执行）/`compose_answer`/`compose_escalate` |
| `loop.py` | `run_turn` 的 ReAct 循环；`TurnResult.to_dict()` 带 `candidates/evidence`（检索可见性）|

## 循环控制 / 安全

- `max_retrieval_rounds`（默认 3）= 一轮内最多检索几次；`max_ask_rounds`（默认 3）= 一次咨询
  最多追问几次；`max_steps`（默认 6）= 一轮内控制器最多迭代几次（兜底，防失控）。三者在
  `stages.decide` / `loop.run_turn` 里**硬性覆盖模型意图**，杜绝无限检索/无限追问。
- 急危重信号 → 控制器直接选 escalate，不再检索或追问。
- 回答只依据「对话 + Evidence」，不暴露 state/prompt/评分/实体ID；证据缺失如实说，不编造。

## 可观察性（检索可见）

- `TurnResult` / `POST /api/kg/agent/chat` 响应始终带 `evidence`（命中实体 + 事实句）、
  `candidates`（候选证候）、分步 `trace`（每步控制器决策 + 检索结果）——不再有 `debug` 开关，
  推理过程对用户默认可见是硬要求，不是可选的调试功能。
- 前端每条助手消息下方常驻候选证候 chips + 「推理过程」时间线（markdown 渲染，默认展开），
  见 `web/src/pages/Chat.jsx` 的 `ReasoningView`/`stepMarkdown`。
- CLI `--trace` 打印每步动作/检索；`scripts/agent_scenarios.py` 打印多轮下钻的全过程。

## 用法

```bash
.venv/bin/python src/agent_cli.py                              # 交互
.venv/bin/python src/agent_cli.py -q "我失眠" --trace
.venv/bin/python scripts/agent_scenarios.py                    # 全部场景
.venv/bin/python scripts/agent_scenarios.py shimian            # 单个
.venv/bin/python -m pytest tests/test_agent_loop.py -q         # 离线回归
```

```bash
curl -s localhost:53785/api/kg/agent/chat -X POST -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"我失眠"}]}'
# → {action, reply, candidates, evidence, trace}
```
