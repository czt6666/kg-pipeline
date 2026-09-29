# TCM 智慧诊疗 Agent Loop（检索驱动版）

一个**检索驱动**的对话决策循环：检索是主干，追问只用来给检索到的分支剪枝。当前打通中医知识
问答与基于症状的初步辨证（分诊/科室/医生推荐预留）。Agent 只决定「现在做什么、检索什么」，
底层检索交给已实现的混合检索模块（`src/retrieval/pipeline.py`）。

代码 `src/agent/`；交互调试 `src/agent_cli.py`；场景回归 `scripts/agent_scenarios.py`；
HTTP 入口 `POST /api/agent/chat`；前端问答页 `web/src/pages/Chat.jsx`（`#/qa`）。

## 核心理念（相对上一版的改动）

上一版有独立的「完整性判断→决定是否检索→检索→判断证据」多段 LLM 决策，会退化成**无限 ASK**
（总觉得信息不够）。本版按用户反馈重构：

- **没有抽象的"要不要检索"阶段**。只要有锚点（症状或名词）就立刻检索。
- **追问是为了剪枝**，且**问题来自知识图谱的候选分支**——检索到多个候选证候后，问一个"能区分
  这些证候"的症状，每次回答都在缩小候选集。
- 事实性问题**直接检索后回答，绝不追问**。
- 追问次数有**硬上限**（`max_ask_rounds`），到顶必须作答。

## 流程

```
用户消息
  → interpret（判 mode + 累计症状 + factual 的 focus 实体/关系）
  → assess_risk
     高风险/急危重/需线下 → ESCALATE（终止）
  mode = other    → 直接回答（不检索）
  mode = factual  → 按 focus 实体+关系检索 → ANSWER（从不追问；证据缺失就如实说没收录）
  mode = consult:
     无症状        → 问一句 bootstrap（"主要哪里不舒服？"）（本轮终止）
     有症状        → 每个症状检索候选证候分支
                      → differential：
                          answer_ready            → ANSWER（给方向 + 治法/方剂）
                          discriminator(还有预算) → ASK 这一个"能区分候选证候"的问题（终止）
```

每轮开头 `new_turn()` 会**清空上一轮 evidence**：consult 每轮都用「累计症状全集」重新检索一次，
不清空就会堆叠重复事实、把 differential 的 prompt 撑爆（这是实测发现并修掉的 bug）。

## 模块（都可单独替换 / 测试）

| 文件 | 职责 |
|---|---|
| `schema_spec.py` | 合法实体/关系；`validate_path` 校验检索路径在 schema 上走得通；护栏：Agent 不能发明类型/关系 |
| `state.py` | `AgentState`：对话、`understanding`(interpret 输出)、`risk`、累计 `symptoms`、`candidates`、`evidence`、`ask_rounds`/`max_ask_rounds`、`trace`；`to_dict()` 可复盘 |
| `actions.py` | Action 枚举、`RetrievalRequest`/`RetrievalQuery`/`Evidence` |
| `reasoner.py` | LLM 边界：`think()`(JSON+一次修复)/`write()`(正文)；`ScriptedReasoner` 供测试 |
| `retrieval_adapter.py` | 请求→`hybrid_search`→归一 `Evidence`，按 path 关系排序；`FakeRetrievalAdapter` 供测试 |
| `prompts.py` | 阶段 prompt：interpret / risk / differential / answer / triage / escalate（运行时 prompt，非 `prompts/*.txt` 生成物）|
| `stages.py` | 各 stage；**检索请求由 interpret 结构化输出程序化拼**（不再让 LLM 生成 schema path，天然合法）|
| `loop.py` | `run_turn` 编排；`TurnResult.to_dict()` 带 `candidates/symptoms/evidence`（检索可见性）|

## 可观察性（检索可见）

- `TurnResult` / `POST /api/agent/chat` 响应始终带 `evidence`（命中实体 + 事实句）、`candidates`
  （候选证候）、`symptoms`；`debug:true` 再加分阶段 `trace`。
- 前端每条助手消息下方常驻「检索依据」面板 + 候选证候 chips。
- CLI `--trace` 打印每阶段输出；不加也会回显本轮「检索依据 / 候选证候」。
- 场景脚本 `scripts/agent_scenarios.py` 打印动作/回复/检索/候选/stage 序列，用来手动盯问题。

## 循环控制 / 安全

- `max_ask_rounds`（默认 3）= 一次咨询最多追问几次；`stages.differential` 到顶强制
  `answer_ready=True`，杜绝无限 ASK。ASK 不额外花 LLM 调用（问题来自 bootstrap 常量或
  differential 的 discriminator）。
- 高风险/急危重/需线下 → ESCALATE，建议就医/急诊，不给可能延误就医的自我处置或处方剂量。
- 回答只依据「对话 + Evidence」，不暴露 state/prompt/评分/实体ID；证据缺失如实说，不编造。

## 用法

```bash
.venv/bin/python src/agent_cli.py                              # 交互
.venv/bin/python src/agent_cli.py -q "柴胡的功效是什么？" --trace
.venv/bin/python scripts/agent_scenarios.py                    # 全部场景
.venv/bin/python scripts/agent_scenarios.py consult_insomnia   # 单个
.venv/bin/python -m pytest tests/test_agent_loop.py -q         # 离线回归
```

```bash
curl -s localhost:53785/api/agent/chat -X POST -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"我最近老是失眠，晚上心烦、口干"}]}'
# → {action, reply, candidates, symptoms, evidence, trace?}
```
