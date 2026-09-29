"""The agent loop -- retrieval-driven.

One user message -> one TurnResult. Retrieval is the backbone; questioning only prunes
retrieved branches. Control flow:

  new turn -> interpret (mode + symptoms + focus) -> assess_risk
    if risk emergency / needs offline / high -> ESCALATE (terminal)

    mode == other    -> answer directly (no retrieval)
    mode == factual  -> retrieve focus entity+relation -> ANSWER (never asks)
    mode == consult:
        if no symptoms yet -> ASK one bootstrap question (terminal for this turn)
        else:
          retrieve symptoms -> candidate 证候 branches
          differential:
            answer_ready              -> ANSWER (方向 + 治法/方剂)
            discriminator (budget>0)  -> ASK that ONE grounded pruning question (terminal)

The loop only orchestrates; every LLM/retrieval touch goes through `reasoner`/`adapter`, so
it runs fully offline in tests. compose_* stages own all user-facing text and are told to
hide internals.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import stages
from .actions import Action
from .retrieval_adapter import RetrievalAdapter
from .schema_spec import SchemaSpec, load_schema_spec
from .state import AgentState


@dataclass
class TurnResult:
    action: str  # terminal Action this turn
    reply: str  # user-facing text
    state: AgentState = field(repr=False, default=None)

    def evidence_view(self) -> list[dict]:
        """Compact, user-safe view of what was retrieved this turn -- for the "检索依据"
        panel (candidates + fact sentences), never internal scores/IDs beyond names."""
        out = []
        for ev in (self.state.evidence if self.state else []):
            if not ev.found:
                out.append({"query": ev.query, "found": False})
                continue
            out.append({
                "query": ev.query,
                "found": True,
                "entity": (ev.resolved_entity or {}).get("name"),
                "type": (ev.resolved_entity or {}).get("type"),
                "facts": [f.sentence for f in ev.facts[:10]],
            })
        return out

    def to_dict(self, include_trace: bool = False) -> dict:
        d = {"action": self.action, "reply": self.reply}
        if self.state is not None:
            d["candidates"] = self.state.candidates
            d["symptoms"] = self.state.symptoms
            d["evidence"] = self.evidence_view()
            if include_trace:
                d["trace"] = [s.to_dict() for s in self.state.trace]
        return d


class TCMAgent:
    def __init__(self, reasoner, adapter: RetrievalAdapter, schema: SchemaSpec):
        self.reasoner = reasoner
        self.adapter = adapter
        self.schema = schema

    @classmethod
    def build(cls, dataset=None, merge=None, max_ask_rounds=3) -> tuple["TCMAgent", AgentState]:
        from common import work_dir
        from llm_client import LLMClient
        from retrieval.summarize import SUMMARY_MODEL

        state = AgentState(max_ask_rounds=max_ask_rounds)
        if dataset:
            state.dataset = dataset
        if merge:
            state.merge = merge
        schema = load_schema_spec(state.dataset)
        wd = work_dir(state.dataset, state.merge)
        client = LLMClient(wd / "llm_cache")
        answer_client = LLMClient(wd / "llm_cache", model=SUMMARY_MODEL)
        from .reasoner import LLMReasoner
        reasoner = LLMReasoner(client, answer_client=answer_client)
        adapter = RetrievalAdapter(state.dataset, state.merge, schema)
        return cls(reasoner, adapter, schema), state

    # ---- the loop ----

    def run_turn(self, state: AgentState, user_message: str) -> TurnResult:
        state.add_user(user_message)
        state.new_turn()

        u = stages.interpret(state, self.reasoner)
        risk = stages.assess_risk(state, self.reasoner)
        if risk.get("emergency") or risk.get("needs_offline") or risk.get("level") == "high":
            return self._escalate(state)

        mode = u.get("mode")

        if mode == "other":
            return self._answer(state)

        if mode == "factual":
            stages.retrieve_focus(state, self.adapter)
            return self._answer(state)

        # mode == consult
        if not state.symptoms:
            return self._ask(state, stages.BOOTSTRAP_ASK)

        stages.retrieve_symptoms(state, self.adapter)
        diff = stages.differential(state, self.reasoner)
        if not diff["answer_ready"] and diff["discriminator"]:
            return self._ask(state, diff["discriminator"]["question"])
        return self._answer(state)

    # ---- terminal wrappers ----

    def _answer(self, state) -> TurnResult:
        text = stages.compose_answer(state, self.reasoner)
        state.add_assistant(text)
        state.end_episode()
        return TurnResult(action=Action.ANSWER, reply=text, state=state)

    def _ask(self, state, question: str) -> TurnResult:
        # The question text is produced upstream (bootstrap constant or differential's
        # grounded discriminator) -- ASK never costs an extra LLM call.
        state.ask_rounds += 1
        state.add_assistant(question)
        return TurnResult(action=Action.ASK, reply=question, state=state)

    def _triage(self, state) -> TurnResult:
        text = stages.compose_triage(state, self.reasoner)
        state.add_assistant(text)
        state.end_episode()
        return TurnResult(action=Action.TRIAGE, reply=text, state=state)

    def _escalate(self, state) -> TurnResult:
        text = stages.compose_escalate(state, self.reasoner)
        state.add_assistant(text)
        state.end_episode()
        return TurnResult(action=Action.ESCALATE, reply=text, state=state)
