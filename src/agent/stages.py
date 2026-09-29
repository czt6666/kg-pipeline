"""Stage functions for the retrieval-driven loop. Each is one prompt-call-parse unit
(or, for retrieval, a deterministic request build + adapter call) and logs a TraceStep so a
run is fully observable. loop.py wires them into the control flow.

Retrieval requests are now built *programmatically* from `interpret`'s structured output
(focus entity/relation, or the symptom list) rather than asking the LLM to emit a schema
path -- fewer moving parts, and the path is always schema-valid by construction.
"""
from __future__ import annotations

from . import prompts
from .actions import RetrievalQuery, RetrievalRequest
from .retrieval_adapter import RetrievalAdapter
from .state import AgentState, timed

# Relation to follow for a factual focus, keyed by the relation the user is asking about.
# Everything here is a real schema relation (schema_spec validates on execution anyway).
_FOCUS_PATHS = {
    "组成": ["组成"], "功效": ["功效"], "主治": ["主治"], "归经": ["归经"],
    "分型": ["分型"], "治法": ["治法"], "方用": ["方用"], "用药": ["用药"],
    "病因": ["病因"], "病位": ["病位"], "表现为": ["表现为"], "鉴别": ["鉴别"],
}

BOOTSTRAP_ASK = ("为了帮您更好地分析，能具体说说主要是哪里不舒服吗？"
                 "比如有哪些症状、持续多久、什么情况下会加重或缓解。")


def _clamp(d: dict, key: str, allowed: set, default):
    v = d.get(key)
    return v if v in allowed else default


def interpret(state: AgentState, reasoner) -> dict:
    ms = timed()
    out = reasoner.think(prompts.interpret_prompt(state), tag="interpret", max_tokens=768)
    out["mode"] = _clamp(out, "mode", {"factual", "consult", "other"}, "consult")
    out.setdefault("symptoms", [])
    out.setdefault("entities", [])
    state.understanding = out
    # Cumulative symptoms are re-derived from the whole transcript each turn, so a follow-up
    # answer naturally folds in.
    if out.get("symptoms"):
        state.symptoms = out["symptoms"]
    state.log("interpret", out, latency_ms=ms())
    return out


def assess_risk(state: AgentState, reasoner) -> dict:
    ms = timed()
    out = reasoner.think(prompts.risk_prompt(state), tag="risk", max_tokens=512)
    out["level"] = _clamp(out, "level", {"low", "medium", "high"}, "low")
    out["emergency"] = bool(out.get("emergency", False))
    out["needs_offline"] = bool(out.get("needs_offline", False))
    state.risk = out
    state.log("risk", out, latency_ms=ms())
    return out


def retrieve_focus(state: AgentState, adapter: RetrievalAdapter) -> None:
    """Factual path: resolve the focus entity and follow the asked relation (if any)."""
    u = state.understanding or {}
    term = (u.get("focus_entity") or "").strip() or u.get("normalized_question", "").strip()
    path = _FOCUS_PATHS.get((u.get("focus_relation") or "").strip(), [])
    seed_type = (u.get("focus_type") or "").strip() or None
    q = RetrievalQuery(term=term, seed_type=seed_type if adapter.schema.is_entity_type(seed_type or "") else None,
                       path=path, focus=u.get("focus_relation", ""))
    _run(state, RetrievalRequest(queries=[q], top_k=12, rationale="factual focus"), adapter)


def retrieve_symptoms(state: AgentState, adapter: RetrievalAdapter) -> None:
    """Consult path: one query per known symptom, surfacing the candidate 证候 branches
    (症状 <--表现为-- 证候, and each 证候's 治法/方用) that questioning will prune."""
    queries = [RetrievalQuery(term=s, seed_type="症状", path=["表现为"], focus="candidate syndromes")
               for s in state.symptoms[:6]]
    if not queries:
        return
    _run(state, RetrievalRequest(queries=queries, top_k=10, rationale="symptom -> candidate syndromes"), adapter)


def _run(state: AgentState, request: RetrievalRequest, adapter: RetrievalAdapter) -> None:
    # Drop queries that would fail schema validation rather than aborting the whole turn.
    errors = adapter.validate(request)
    if errors:
        request = RetrievalRequest(
            queries=[q for q in request.queries
                     if not adapter.validate(RetrievalRequest(queries=[q]))],
            top_k=request.top_k, rationale=request.rationale)
        if not request.queries:
            state.log("retrieval_skipped", {"errors": errors})
            return
    ms = timed()
    evidence = adapter.retrieve(request)
    state.evidence.extend(evidence)
    state.retrieval_history.append(request)
    state.retrieval_rounds += 1
    state.log("retrieval_result",
              {"queries": [q.to_dict() for q in request.queries],
               "evidence": [e.to_dict() for e in evidence]}, latency_ms=ms())


def differential(state: AgentState, reasoner) -> dict:
    ms = timed()
    out = reasoner.think(prompts.differential_prompt(state), tag="differential", max_tokens=1024)
    out["answer_ready"] = bool(out.get("answer_ready", True))
    out.setdefault("candidates", [])
    disc = out.get("discriminator")
    if not (isinstance(disc, dict) and (disc.get("question") or "").strip()):
        out["discriminator"] = None
    # Hard cap: past the ask budget, never ask again whatever the model wants.
    if state.ask_rounds >= state.max_ask_rounds:
        out["answer_ready"] = True
        out["discriminator"] = None
        out["capped"] = True
    state.candidates = out["candidates"]
    state.log("differential", out, latency_ms=ms())
    return out


def compose_answer(state: AgentState, reasoner) -> str:
    ms = timed()
    text = reasoner.write(prompts.answer_prompt(state), tag="answer", max_tokens=1200)
    state.log("answer", {"mode": (state.understanding or {}).get("mode")}, latency_ms=ms())
    return text


def compose_triage(state: AgentState, reasoner) -> str:
    ms = timed()
    text = reasoner.write(prompts.triage_prompt(state), tag="triage", max_tokens=768)
    state.log("triage", {}, latency_ms=ms())
    return text


def compose_escalate(state: AgentState, reasoner) -> str:
    ms = timed()
    text = reasoner.write(prompts.escalate_prompt(state), tag="escalate", max_tokens=512)
    state.log("escalate", {}, latency_ms=ms())
    return text
