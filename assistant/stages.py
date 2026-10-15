"""Stage functions for the single-controller loop. Each is one prompt-call-parse unit (or,
for retrieval, a deterministic request build + adapter call) and logs a TraceStep so a run is
fully observable. loop.py wires them into the ReAct control flow.

There are only four:
  - `decide`         -- one controller LLM call -> next action (retrieve/ask/answer/escalate).
  - `run_retrieval`  -- execute the controller's queries against the hybrid retrieval module.
  - `compose_answer` / `compose_escalate` -- turn collected evidence into prose.

The controller only names entities to look up; the graph supplies the relations, so the agent
structurally cannot invent schema paths (the old schema-path-emitting prompt is gone). An
optional `focus` on a query just re-ranks which of the hit entity's facts surface first.
"""
from __future__ import annotations

from . import prompts
from .actions import Action, RetrievalQuery, RetrievalRequest
from .retrieval_adapter import RetrievalAdapter
from .schema_spec import SchemaSpec
from .state import AgentState, timed

_VALID_ACTIONS = {"retrieve", "ask", "answer", "escalate"}

# focus keyword -> schema relation, used only to prioritise facts of a hit entity (not to
# drive graph traversal -- the adapter already returns multi-hop facts).
_FOCUS_RELATION = {
    "组成": "组成", "方剂": "方用", "方": "方用", "治法": "治法", "用药": "用药", "中药": "用药",
    "功效": "功效", "主治": "主治", "归经": "归经", "分型": "分型", "证候": "分型",
    "病因": "病因", "病位": "病位", "症状": "表现为", "表现": "表现为", "鉴别": "鉴别",
}


def decide(state: AgentState, reasoner, schema: SchemaSpec) -> dict:
    """The controller: one LLM call that returns the next action. Everything downstream is
    deterministic, so this is the only place per step the agent 'thinks'."""
    ms = timed()
    out = reasoner.think(prompts.controller_prompt(state, schema), tag="controller",
                         on_thinking=state.thinking_sink("controller"))
    action = out.get("action")
    if action not in _VALID_ACTIONS:
        # If the model returned something odd, fall back to retrieving if we never have, else
        # answering with what we've got -- never crash the turn.
        action = "retrieve" if state.retrieval_rounds == 0 else "answer"
    out["action"] = action
    out.setdefault("queries", [])
    out.setdefault("question", "")
    out.setdefault("candidates", [])
    # Hard caps override the model: no asking past budget, no retrieving past budget.
    if action == "ask" and state.ask_rounds >= state.max_ask_rounds:
        out["action"] = "answer"
        out["capped"] = "ask_budget"
    if action == "retrieve" and state.retrieval_rounds >= state.max_retrieval_rounds:
        out["action"] = "answer"
        out["capped"] = "retrieval_budget"
    if out["candidates"]:
        state.candidates = out["candidates"]
    state.understanding = out  # keep the latest decision for inspection / answer context
    state.log("controller", out, latency_ms=ms())
    return out


def run_retrieval(state: AgentState, adapter: RetrievalAdapter, raw_queries: list[dict]) -> None:
    """Build a RetrievalRequest from the controller's queries and execute it. Queries missing a
    term, or naming an invalid seed_type, are dropped rather than aborting the turn."""
    queries = []
    seen_terms = set()
    for q in raw_queries or []:
        term = (q.get("term") or "").strip()
        if not term or term in seen_terms:
            continue
        seen_terms.add(term)
        stype = (q.get("type") or "").strip()
        if stype and not adapter.schema.is_entity_type(stype):
            stype = ""
        focus = (q.get("focus") or "").strip()
        rel = _FOCUS_RELATION.get(focus, focus if adapter.schema.is_relation(focus) else "")
        queries.append(RetrievalQuery(term=term, seed_type=stype or None,
                                      path=[rel] if rel else [], focus=focus))
    if not queries:
        state.log("retrieval_skipped", {"reason": "no valid query term"})
        return
    request = RetrievalRequest(queries=queries, top_k=10, rationale="controller")
    ms = timed()
    evidence = adapter.retrieve(request)
    state.evidence.extend(evidence)
    state.retrieval_history.append(request)
    state.retrieval_rounds += 1
    state.log("retrieval_result",
              {"queries": [q.to_dict() for q in queries],
               "evidence": [e.to_dict() for e in evidence]}, latency_ms=ms())


def compose_answer(state: AgentState, reasoner) -> str:
    ms = timed()
    text = reasoner.write(prompts.answer_prompt(state), tag="answer", on_text=state.text_sink(),
                          on_thinking=state.thinking_sink("answer"))
    state.log("answer", {"candidates": state.candidates}, latency_ms=ms())
    return text


def compose_escalate(state: AgentState, reasoner) -> str:
    ms = timed()
    text = reasoner.write(prompts.escalate_prompt(state), tag="escalate", on_text=state.text_sink(),
                          on_thinking=state.thinking_sink("escalate"))
    state.log("escalate", {}, latency_ms=ms())
    return text
