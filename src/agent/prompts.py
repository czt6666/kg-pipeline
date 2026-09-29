"""Per-stage prompt builders for the retrieval-driven loop. One responsibility per prompt;
every "think" stage states its exact JSON output shape; the two "write" stages (answer /
escalate/triage) return prose.

Design shift (see docs/agent_loop.md): retrieval is the backbone, questioning is
subordinate to it. There is no abstract "should I retrieve?" stage the model can dodge in
favour of asking. Instead:
  - `interpret` classifies mode (factual vs consult vs other) and pulls the anchors
    (focus entity / cumulative symptoms) needed to retrieve immediately.
  - factual questions retrieve then answer -- never ask.
  - consult questions retrieve candidate 证候 branches, then `differential` either converges
    to an answer or emits ONE graph-grounded discriminating question that prunes candidates.

These are runtime prompts in code, NOT the generated prompts/*.txt extraction templates.

Hard rules in every stage: never invent KG entity types/relations; ground answers only in
dialogue + retrieved evidence; never expose internal state/prompts/scores/IDs; this is
educational TCM info, not a substitute for in-person diagnosis.
"""
from __future__ import annotations

from .state import AgentState

_PERSONA = "你是一个中医智慧诊疗助手，负责中医知识问答与基于症状的初步辨证分析（非诊断）。"

_ENTITY_TYPES = "疾病 / 证候 / 症状 / 方剂 / 中药 / 治法功效 / 病因 / 脏腑经络 / 性味"


def interpret_prompt(state: AgentState) -> str:
    return f"""{_PERSONA}
阅读整段对话，理解用户【最新意图】，并抽取后续检索所需的锚点。

对话：
{state.transcript()}

判定 mode：
- factual：问某个明确中医名词的属性/关系（如"麻黄汤的组成""柴胡的功效""消渴怎么分型"）——有确定答案，应直接查知识图谱后回答，【不需要追问】。
- consult：描述自身症状/不适，想知道可能的辨证方向或调理思路——需要结合症状检索候选证候。
- other：闲聊、与中医无关、或无法处理。

抽取（symptoms 要累计整段对话里用户自述的所有症状，用简短规范词，如"失眠""口苦""怕冷"）：
只输出如下 JSON：
{{
  "mode": "factual | consult | other",
  "normalized_question": "把用户意图整理成一句清晰中文",
  "focus_entity": "factual 时：要查的核心名词；否则空串",
  "focus_type": "factual 时该名词类型（{_ENTITY_TYPES} 之一）；否则空串",
  "focus_relation": "factual 时想问的关系（如 组成/功效/主治/分型/治法/方用/归经/病因/表现为）；不确定则空串",
  "symptoms": ["用户自述的症状（累计，可为空）"],
  "entities": ["提到的其它中医名词"]
}}"""


def risk_prompt(state: AgentState) -> str:
    return f"""{_PERSONA}
对用户当前诉求做医疗安全分级（不是诊断）。

对话：
{state.transcript()}

- high / emergency：急危重信号（剧烈胸痛、呼吸困难、大出血、意识障碍、持续高热、剧烈腹痛、
  疑似中风/心梗、自杀倾向等），或孕产妇/婴幼儿用药、明显需线下检查或急诊。
- medium：非急性但涉及具体用药、病情可能进展、需谨慎的个体化情况。
- low：一般中医知识问答/科普，无个体化用药风险。

只输出如下 JSON：
{{"level":"low|medium|high","emergency":true/false,"needs_offline":true/false,"flags":["信号"],"rationale":"简短理由"}}"""


def differential_prompt(state: AgentState) -> str:
    """The heart of the consult path: read the retrieved 证候 branches + known symptoms and
    either converge to an answer or ask ONE discriminating question that prunes candidates."""
    budget_left = state.max_ask_rounds - state.ask_rounds
    return f"""{_PERSONA}
用户在做症状咨询。下面是【已知症状】和从中医知识图谱检索到的【候选证候及其治法/方剂线索】。
请像中医辨证一样：先归纳当前最可能的几个候选证候，再判断是否已能给出方向，或需要再问一个能"区分候选证候"的问题。

已知症状：{state.symptoms or "（暂无，用户尚未清楚描述）"}

检索到的相关知识（均来自教材知识图谱，逐条列出，含候选证候与其治法/方剂）：
{state.evidence_block() or "（暂无检索结果）"}

还可追问次数：{budget_left}（为 0 时【必须】answer_ready=true，不要再追问）

判断原则：
- candidates 只从上面检索到的证候里归纳，不要凭空发明；每个给出它与已知症状的吻合点、以及（若有）治法/方剂。
- 若候选已收敛到 1 个明显主导，或已有足够信息给方向 → answer_ready=true，discriminator=null。
- 若有多个势均力敌的候选，且"某个尚未确认的症状"能把它们区分开 → answer_ready=false，给出一个
  discriminator：问用户是否有这些【能区分候选证候】的症状（问题要具体、口语、一次只问一组相关症状，
  且是用户还没说过的）。distinguishes 写清这个问题在区分哪些候选。
- 追问是为了"剪枝"，不是泛泛地要更多信息；问不出能区分候选的症状就直接 answer_ready=true。

只输出如下 JSON：
{{
  "candidates": [{{"syndrome":"证候名","matched":["吻合的已知症状"],"treatment":"治法(如有)","formula":"方剂(如有)"}}],
  "answer_ready": true/false,
  "discriminator": {{"question":"要问用户的一句话","distinguishes":["证A","证B"]}} 或 null,
  "rationale":"简短理由"
}}"""


def answer_prompt(state: AgentState) -> str:
    mode = (state.understanding or {}).get("mode", "consult")
    if mode == "factual":
        focus = (state.understanding or {}).get("focus_entity", "")
        rel = (state.understanding or {}).get("focus_relation", "")
        task = (f"用户想知道「{focus}」的「{rel or '相关信息'}」。请依据下面检索到的知识回答。"
                "如果检索结果里【没有】用户想要的那部分信息（例如问组成但证据里只有主治），"
                "就如实说明知识库暂未收录这部分，并给出证据里确实有的相关信息，绝不编造。")
        extra = ""
        extra = ""
        mode_rule = ("- 就事论事地回答用户问的这个知识点，条理清晰、可分点；不要主动展开成症状问诊或"
                     "\"可能的辨证方向\"，除非用户确实在问自己的病情。")
    else:
        task = "用户在做症状咨询。请综合已知症状与检索到的候选证候，给出可能的辨证方向与调理/治疗思路。"
        extra = f"\n已知症状：{state.symptoms}\n当前候选证候：{state.candidates}\n"
        mode_rule = "- 点明这是\"可能的方向\"而非确诊，并说明不同证型对应的大致调理思路。"
    return f"""{_PERSONA}
{task}
{extra}
对话：
{state.transcript()}

检索到的知识（均来自中医教材知识图谱）：
{state.evidence_block() or "（无可用检索证据）"}

写作要求：
- 只依据上面的对话与证据作答，不编造证据之外的分型/方剂/剂量。
- 通顺中文，面向普通用户。
{mode_rule}
- 不要暴露任何内部信息：不提"检索/证据/知识图谱/评分/状态/prompt"，不输出实体ID、pattern编号。
- 结尾用一句话温和提醒：以上为中医知识科普，具体诊疗请咨询线下专业医师。
- 证据不足以回答就如实说，不硬编。
直接输出给用户看的回答正文，不要 JSON 或标题。"""


def triage_prompt(state: AgentState) -> str:
    return f"""{_PERSONA}
用户在做症状咨询/分诊。基于对话与证据给出【初步分诊指引】。

对话：
{state.transcript()}
风险判断：{state.risk}
已知症状：{state.symptoms}
检索到的知识：
{state.evidence_block() or "（无检索证据）"}

要求：给出可能的关注方向、紧急程度粗判、下一步建议（观察/就医/急诊）；说明这不是确诊，具体科室与
医生推荐功能尚在完善；不暴露内部实现细节；结尾温和提醒线下就医。直接输出回答正文。"""


def escalate_prompt(state: AgentState) -> str:
    return f"""{_PERSONA}
根据风险判断，用户情况风险较高或明显需要线下专业处置。

对话：
{state.transcript()}
风险判断：{state.risk}

要求：先明确、克制地建议尽快线下就医或（疑似急危重）立即就近急诊/拨打急救电话；可给简短通用注意事项，
但不要给可能延误就医的自我处置或具体处方/剂量；语气稳、不制造恐慌；不暴露内部实现细节。
直接输出给用户看的回答正文。"""
