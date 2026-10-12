"""Prompts for the single-controller (ReAct-style) TCM agent loop.

First-principles design (see docs/agent_loop.md): a 看病 agent is one reasoning loop with a
retrieval tool, like Claude Code's agent loop -- not a fixed pipeline of specialised stages.
So there are only two kinds of prompt:

  - `controller_prompt`  -- the brain. Each step it reads {对话 + 本体图 + 已检索证据 + 预算},
    and picks ONE action: retrieve / ask / answer / escalate. This single call subsumes the
    old interpret + risk + differential + routing stages.
  - `answer_prompt` / `escalate_prompt` -- the mouth. Turn the collected evidence into prose.

Why this shape fixes the reported failures:
  - 循环提问: the controller sees the WHOLE transcript (its own past questions + the user's
    answers) plus how many questions it already asked, and is told never to re-ask -- so it
    can't lose the goal or loop on one question.
  - 精简: 2 prompt kinds instead of 6 stages; risk is folded into the controller.
  - 多轮检索: the loop re-invokes the controller after each retrieval, so it can drill down
    (病 → 证候 → 方剂/中药) over several rounds before answering.
  - 本体认知: the KG ontology (entity types + relations + canonical paths) is injected so the
    controller knows what to look up and how the graph connects.

These are runtime prompts in code, NOT the generated resources/prompts/*/*.txt extraction
templates. Hard rules everywhere: ground only in dialogue + retrieved evidence; never invent
entities/relations; never expose internal state/scores/IDs; educational TCM info, not a
substitute for in-person diagnosis.
"""
from __future__ import annotations

from .schema_spec import SchemaSpec
from .state import AgentState

_PERSONA = ("你是一名中医智慧诊疗助手。你的工作方式像一个会用检索工具的医生：先查中医教材知识图谱，"
            "再基于查到的证据做辨证、给方向。你负责中医知识问答，以及根据症状做初步辨证（给可能的证型、"
            "治法、方剂/中药方向，非确诊）。")


def controller_prompt(state: AgentState, schema: SchemaSpec) -> str:
    """The decision brain. Returns a JSON action. The loop executes it and loops back."""
    ask_left = state.max_ask_rounds - state.ask_rounds
    retr_left = state.max_retrieval_rounds - state.retrieval_rounds
    return f"""{_PERSONA}

【知识图谱本体（你检索的对象，只认识这些类型/关系，不要发明别的）】
{schema.vocabulary_block()}

【当前对话】
{state.transcript()}

【到目前为止已检索到的证据】（本轮累计，均来自上面的知识图谱）
{state.evidence_block() or "（还没有检索过，先去检索）"}

【预算】本轮还能检索 {retr_left} 次；本次咨询还能追问 {ask_left} 次。

你要决定【下一步做什么】，四选一：
- retrieve：还需要从知识图谱查东西才能回答。给出要查的实体名（term）。
    · 诊疗三步走：① 先查主诉对应的「疾病/症状」，拿到候选【证候】；② 再查选定的【证候】，
      拿到它的【治法/方剂/常用药】；③ 需要具体药物组成时再查【方剂】。缺哪一步就查哪一步。
    · term 用知识图谱里会出现的规范中医词（如"感冒""失眠""心肾不交证""交泰丸"），不要查整句话。
    · 一次可给多个 term（如同时查几个症状）；但别重复查已经查过且命中的实体。
- ask：只有当「多个候选证候难以区分、且某个患者还没说过的症状能区分它们」时，才问一句。
    · 问题必须来自已检索到的证候分支（是为了剪枝），具体、口语、一次只问一组相关症状。
    · 绝不重复问对话里已经问过或用户已回答过的内容。预算为 0 时【禁止】再 ask。
- answer：已经查到足够证据给出知识点回答、或给出辨证方向（证型+治法+方剂/中药）时选它。
    · 事实性问题（问某名词的属性/关系）查到就直接 answer，不要追问。
    · 证据已指向某个明显主导证候，或追问预算用尽 → answer。
- escalate：出现急危重信号（剧烈胸痛、呼吸困难、大出血、意识障碍、持续高热、剧烈腹痛、疑似中风/心梗、
    自杀倾向等），或孕产妇/婴幼儿用药、明显需要线下检查 → 立即 escalate，不再检索或追问。

只输出一个 JSON 对象：
{{
  "action": "retrieve | ask | answer | escalate",
  "queries": [{{"term":"要查的实体名","type":"可选的实体类型提示","focus":"想了解它的什么(如 证候/治法/方剂/组成)"}}],
  "question": "action=ask 时：要问患者的一句话；否则空串",
  "candidates": [{{"syndrome":"当前最可能的证候名","note":"与已知症状的吻合点/治法/方剂线索"}}],
  "rationale": "一句话说明你为什么这么决定"
}}
只有 action=retrieve 时才需要 queries；只有 action=ask 时才需要 question；candidates 尽量根据已检索证据填写（没有就空数组）。"""


def answer_prompt(state: AgentState) -> str:
    """The mouth. Compose the final reply from dialogue + collected evidence. One prompt for
    both factual answers and consult directions -- the model adapts from the conversation."""
    cands = state.candidates
    cand_line = ("\n当前最可能的证候（供参考，需在正文体现对应治法/方剂方向）：" + str(cands)) if cands else ""
    return f"""{_PERSONA}

请根据【对话】和【检索到的证据】给用户一个清楚、可用的回答。

【对话】
{state.transcript()}

【检索到的证据】（均来自中医教材知识图谱）
{state.evidence_block() or "（无可用检索证据）"}
{cand_line}

写作要求：
- 只依据上面的对话与证据作答，不编造证据之外的证型/方剂/中药/剂量；证据不足就如实说，不硬编。
- 如果用户是在问某个中医知识点（如某药功效、某病分型）：就事论事、条理清晰地回答，不要硬扯成问诊。
- 如果用户在描述自己的不适：给出「可能的辨证方向」——点明这是方向而非确诊，说明主要考虑的证型、
  对应的治法与方剂/中药思路；若有多个证型，分别简述区别。
- 通顺中文，面向普通用户，可分点。
- 不要暴露任何内部信息：不提"检索/证据/知识图谱/评分/状态/候选/prompt"，不输出实体ID或编号。
- 结尾用一句话温和提醒：以上为中医知识科普，具体诊疗请咨询线下专业医师。
直接输出给用户看的回答正文，不要 JSON、不要标题。"""


def escalate_prompt(state: AgentState) -> str:
    return f"""{_PERSONA}
用户的情况出现较高风险信号或明显需要线下专业处置。

【对话】
{state.transcript()}

要求：先明确、克制地建议尽快线下就医，或（疑似急危重）立即就近急诊/拨打急救电话；可给简短通用注意事项，
但不要给可能延误就医的自我处置或具体处方/剂量；语气稳、不制造恐慌；不暴露内部实现细节。
直接输出给用户看的回答正文。"""
