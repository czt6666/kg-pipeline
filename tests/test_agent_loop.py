"""Agent loop tests -- fully offline (ScriptedReasoner + FakeRetrievalAdapter, no network,
no graph data). Run: .venv/bin/python -m pytest tests/test_agent_loop.py -q

Covers the retrieval-driven loop: schema guardrail, factual fast-path (never asks), consult
convergence (ANSWER) vs pruning (ASK with a grounded discriminator), the vague-input single
bootstrap ASK, the risk gate, and the ask-budget cap that kills endless-ASK.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agent import stages  # noqa: E402
from agent.actions import Action, Evidence, EvidenceFact  # noqa: E402
from agent.loop import TCMAgent  # noqa: E402
from agent.reasoner import ScriptedReasoner, extract_json  # noqa: E402
from agent.retrieval_adapter import FakeRetrievalAdapter  # noqa: E402
from agent.schema_spec import CANONICAL_PATHS, load_schema_spec  # noqa: E402
from agent.state import AgentState  # noqa: E402


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


def test_validate_path_rejects_disconnected_chain(schema):
    ok, _ = schema.validate_path("中药", ["分型"])
    assert not ok


def test_symptom_to_syndrome_path_validates(schema):
    # The consult retrieval builds 症状 --表现为--> queries; must be schema-valid.
    ok, _ = schema.validate_path("症状", ["表现为"])
    assert ok


def test_extract_json_tolerates_fences():
    assert extract_json('前言\n```json\n{"a": 1}\n```\n后语') == {"a": 1}


# ---- helpers ----

def _fact(sent, rels):
    return EvidenceFact(sentence=sent, source="P-TEST", relations=rels)


def _agent(script, schema, evidence=None, max_ask_rounds=3):
    reasoner = ScriptedReasoner(script)
    adapter = FakeRetrievalAdapter(schema, evidence or {})
    return TCMAgent(reasoner, adapter, schema), AgentState(max_ask_rounds=max_ask_rounds)


# ---- loop routing ----

def test_risk_gate_escalates_before_differential(schema):
    script = {
        "interpret": {"mode": "consult", "symptoms": ["胸痛"], "entities": []},
        "risk": {"level": "high", "emergency": True, "needs_offline": True, "flags": ["胸痛"]},
        "escalate": "请立即拨打120或就近急诊。",
    }
    agent, state = _agent(script, schema)
    r = agent.run_turn(state, "我突然剧烈胸痛喘不上气")
    assert r.action == Action.ESCALATE and "急诊" in r.reply


def test_factual_retrieves_and_answers_without_asking(schema):
    ev = {"柴胡": Evidence(query="柴胡", found=True,
                           resolved_entity={"entity_id": "h1", "name": "柴胡", "type": "中药"},
                           facts=[_fact("柴胡功效为疏肝解郁、和解退热", ["功效"])])}
    script = {
        "interpret": {"mode": "factual", "focus_entity": "柴胡", "focus_type": "中药",
                      "focus_relation": "功效", "symptoms": [], "entities": ["柴胡"]},
        "risk": {"level": "low", "emergency": False, "needs_offline": False},
        "answer": "柴胡的功效主要是疏肝解郁、和解退热。以上为科普，具体请咨询线下医师。",
    }
    agent, state = _agent(script, schema, ev)
    r = agent.run_turn(state, "柴胡的功效是什么？")
    assert r.action == Action.ANSWER
    assert "疏肝" in r.reply
    assert state.retrieval_rounds == 1 and state.evidence[0].found


def test_vague_consult_asks_one_bootstrap_question(schema):
    script = {
        "interpret": {"mode": "consult", "symptoms": [], "entities": []},
        "risk": {"level": "low", "emergency": False, "needs_offline": False},
    }
    agent, state = _agent(script, schema)
    r = agent.run_turn(state, "我最近很不舒服")
    assert r.action == Action.ASK
    assert r.reply == stages.BOOTSTRAP_ASK
    assert state.ask_rounds == 1
    # no retrieval / differential happened
    assert state.retrieval_rounds == 0 and not state.candidates


def test_consult_with_symptoms_prunes_with_grounded_question(schema):
    ev = {"失眠": Evidence(query="失眠", found=True,
                           resolved_entity={"entity_id": "s1", "name": "失眠", "type": "症状"},
                           facts=[_fact("心肾不交证表现为失眠", ["表现为"]),
                                  _fact("气阴两虚证表现为失眠", ["表现为"])])}
    script = {
        "interpret": {"mode": "consult", "symptoms": ["失眠"], "entities": []},
        "risk": {"level": "low", "emergency": False, "needs_offline": False},
        "differential": {"candidates": [{"syndrome": "心肾不交证"}, {"syndrome": "气阴两虚证"}],
                         "answer_ready": False,
                         "discriminator": {"question": "您是否伴有腰膝酸软、耳鸣？",
                                           "distinguishes": ["心肾不交证", "气阴两虚证"]}},
    }
    agent, state = _agent(script, schema, ev)
    r = agent.run_turn(state, "我最近老失眠")
    assert r.action == Action.ASK
    assert r.reply == "您是否伴有腰膝酸软、耳鸣？"  # grounded discriminator, verbatim
    assert state.retrieval_rounds == 1
    assert [c["syndrome"] for c in state.candidates] == ["心肾不交证", "气阴两虚证"]


def test_consult_converges_to_answer(schema):
    ev = {"失眠": Evidence(query="失眠", found=True,
                           resolved_entity={"entity_id": "s1", "name": "失眠", "type": "症状"},
                           facts=[_fact("心肾不交证表现为失眠；心肾不交证治法为交通心肾", ["表现为", "治法"])])}
    script = {
        "interpret": {"mode": "consult", "symptoms": ["失眠", "腰膝酸软", "耳鸣"], "entities": []},
        "risk": {"level": "low", "emergency": False, "needs_offline": False},
        "differential": {"candidates": [{"syndrome": "心肾不交证", "treatment": "交通心肾"}],
                         "answer_ready": True, "discriminator": None},
        "answer": "综合来看比较倾向心肾不交，调理以交通心肾为主。以上为科普，请咨询线下医师。",
    }
    agent, state = _agent(script, schema, ev)
    r = agent.run_turn(state, "还伴有腰膝酸软、耳鸣")
    assert r.action == Action.ANSWER
    assert "心肾不交" in r.reply


def test_ask_budget_cap_forces_answer_ready(schema):
    # At the ask budget, differential must flip answer_ready=True even if the model asks to
    # keep asking -- the hard cap that kills endless-ASK.
    reasoner = ScriptedReasoner({"differential": {
        "candidates": [{"syndrome": "A"}, {"syndrome": "B"}],
        "answer_ready": False,
        "discriminator": {"question": "还想再问...", "distinguishes": ["A", "B"]},
    }})
    state = AgentState(max_ask_rounds=2)
    state.ask_rounds = 2  # budget exhausted
    out = stages.differential(state, reasoner)
    assert out["answer_ready"] is True and out["discriminator"] is None and out.get("capped")
