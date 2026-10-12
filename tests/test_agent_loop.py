"""Agent loop tests -- fully offline (ScriptedReasoner + FakeRetrievalAdapter, no network, no
graph data). Run: .venv/bin/python -m pytest tests/test_agent_loop.py -q

Covers the single-controller ReAct loop: schema guardrail, the controller's retrieve->answer
path, multi-round drill-down retrieval, the ASK pruning action + its hard budget cap (kills
circular questioning), the retrieval budget cap, and the escalate hand-off.
"""
import pytest

from assistant.actions import Action, Evidence, EvidenceFact
from assistant.loop import TCMAgent
from assistant.reasoner import ScriptedReasoner, extract_json
from assistant.retrieval_adapter import FakeRetrievalAdapter
from assistant.schema_spec import CANONICAL_PATHS, load_schema_spec
from assistant.state import AgentState


@pytest.fixture
def schema():
    return load_schema_spec("TCM")


# ---- schema guardrail ----

def test_canonical_paths_are_all_valid(schema):
    for label, (seed, path) in CANONICAL_PATHS.items():
        ok, errs = schema.validate_path(seed, path)
        assert ok, f"canonical path {label} should validate: {errs}"


def test_validate_path_rejects_unknown_relation(schema):
    ok, errs = schema.validate_path("疾病", ["分型", "不存在的关系"])
    assert not ok and any("不存在的关系" in e for e in errs)


def test_vocabulary_block_lists_types_and_relations(schema):
    vb = schema.vocabulary_block()
    assert "实体类型" in vb and "分型" in vb and "常用检索路径" in vb


def test_extract_json_tolerates_fences():
    assert extract_json('前言\n```json\n{"a": 1}\n```\n后语') == {"a": 1}


# ---- helpers ----

def _fact(sent, rels):
    return EvidenceFact(sentence=sent, source="P-TEST", relations=rels)


def _agent(script, schema, evidence=None, max_ask_rounds=3, max_steps=6):
    reasoner = ScriptedReasoner(script)
    adapter = FakeRetrievalAdapter(schema, evidence or {})
    return TCMAgent(reasoner, adapter, schema, max_steps=max_steps), AgentState(max_ask_rounds=max_ask_rounds)


# ---- loop behaviour ----

def test_controller_retrieves_then_answers(schema):
    ev = {"柴胡": Evidence(query="柴胡", found=True,
                           resolved_entity={"entity_id": "h1", "name": "柴胡", "type": "中药"},
                           facts=[_fact("柴胡功效为疏肝解郁、和解退热", ["功效"])])}
    script = {"controller": [
        {"action": "retrieve", "queries": [{"term": "柴胡", "focus": "功效"}]},
        {"action": "answer"},
    ], "answer": "柴胡的功效主要是疏肝解郁、和解退热。以上为科普，具体请咨询线下医师。"}
    agent, state = _agent(script, schema, ev)
    r = agent.run_turn(state, "柴胡的功效是什么？")
    assert r.action == Action.ANSWER
    assert "疏肝" in r.reply
    assert state.retrieval_rounds == 1 and state.evidence[0].found


def test_multi_round_drilldown_retrieval(schema):
    # 感冒 (disease) -> candidate 证候; then drill into the chosen 证候 for its 方剂 before
    # answering. Two retrieval rounds in a single turn, driven by the controller.
    ev = {
        "感冒": Evidence(query="感冒", found=True,
                         resolved_entity={"entity_id": "d1", "name": "感冒", "type": "疾病"},
                         facts=[_fact("感冒分型为风寒束表证；风寒束表证方用荆防败毒散", ["分型", "方用"])]),
        "风寒束表证": Evidence(query="风寒束表证", found=True,
                              resolved_entity={"entity_id": "s1", "name": "风寒束表证", "type": "证候"},
                              facts=[_fact("风寒束表证治法为辛温解表；方用荆防败毒散", ["治法", "方用"])]),
    }
    script = {"controller": [
        {"action": "retrieve", "queries": [{"term": "感冒", "focus": "证候"}]},
        {"action": "retrieve", "queries": [{"term": "风寒束表证", "focus": "方剂"}],
         "candidates": [{"syndrome": "风寒束表证"}]},
        {"action": "answer", "candidates": [{"syndrome": "风寒束表证"}]},
    ], "answer": "考虑风寒束表，治以辛温解表，可参考荆防败毒散方向。以上为科普，请咨询线下医师。"}
    agent, state = _agent(script, schema, ev)
    r = agent.run_turn(state, "我感冒了，怕冷、鼻塞流清涕")
    assert r.action == Action.ANSWER
    assert state.retrieval_rounds == 2
    assert [c["syndrome"] for c in state.candidates] == ["风寒束表证"]


def test_ask_is_a_pruning_question(schema):
    ev = {"失眠": Evidence(query="失眠", found=True,
                           resolved_entity={"entity_id": "s1", "name": "失眠", "type": "症状"},
                           facts=[_fact("心肾不交证表现为失眠", ["表现为"]),
                                  _fact("气阴两虚证表现为失眠", ["表现为"])])}
    script = {"controller": [
        {"action": "retrieve", "queries": [{"term": "失眠"}]},
        {"action": "ask", "question": "您是否伴有腰膝酸软、耳鸣？",
         "candidates": [{"syndrome": "心肾不交证"}, {"syndrome": "气阴两虚证"}]},
    ]}
    agent, state = _agent(script, schema, ev)
    r = agent.run_turn(state, "我最近老失眠")
    assert r.action == Action.ASK
    assert r.reply == "您是否伴有腰膝酸软、耳鸣？"
    assert state.ask_rounds == 1 and state.retrieval_rounds == 1
    assert [c["syndrome"] for c in state.candidates] == ["心肾不交证", "气阴两虚证"]


def test_ask_budget_cap_forces_answer(schema):
    # Budget exhausted: even though the controller wants to ASK, decide() flips it to answer --
    # the hard cap that kills endless questioning.
    script = {"controller": [{"action": "ask", "question": "再问一个..."}],
              "answer": "综合来看给您一个方向。以上为科普，请咨询线下医师。"}
    agent, state = _agent(script, schema, max_ask_rounds=2)
    state.ask_rounds = 2  # no budget left
    r = agent.run_turn(state, "还伴有什么")
    assert r.action == Action.ANSWER


def test_retrieval_budget_cap_forces_answer(schema):
    script = {"controller": [{"action": "retrieve", "queries": [{"term": "x"}]}],
              "answer": "就目前信息给您一个方向。以上为科普，请咨询线下医师。"}
    agent, state = _agent(script, schema)
    state.retrieval_rounds = state.max_retrieval_rounds  # no budget left
    r = agent.run_turn(state, "随便问")
    assert r.action == Action.ANSWER
    assert state.retrieval_rounds == state.max_retrieval_rounds  # no extra retrieval happened


def test_escalate_on_red_flag(schema):
    script = {"controller": [{"action": "escalate"}],
              "escalate": "请立即拨打120或就近急诊。"}
    agent, state = _agent(script, schema)
    r = agent.run_turn(state, "我突然剧烈胸痛喘不上气")
    assert r.action == Action.ESCALATE and "急诊" in r.reply
    assert state.retrieval_rounds == 0  # escalation short-circuits retrieval


def test_max_steps_backstop_answers(schema):
    # Controller keeps trying to retrieve forever; max_steps backstop must still terminate.
    ev = {"x": Evidence(query="x", found=True,
                        resolved_entity={"entity_id": "e", "name": "x", "type": "症状"},
                        facts=[_fact("x", ["表现为"])])}
    script = {"controller": {"action": "retrieve", "queries": [{"term": "x"}]},
              "answer": "给个方向。以上为科普，请咨询线下医师。"}
    agent, state = _agent(script, schema, ev, max_steps=3)
    r = agent.run_turn(state, "测试")
    assert r.action == Action.ANSWER
    assert state.retrieval_rounds <= state.max_retrieval_rounds
