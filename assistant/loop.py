"""The agent loop -- a single-controller ReAct loop (Claude-Code-style tool loop).

One user message -> one TurnResult. Each step the controller decides one action; retrieval is
the tool it calls, and the loop feeds the results straight back so the controller can drill
down over several rounds before it answers:

    new turn:
      repeat up to max_steps:
        decision = controller(transcript + ontology + evidence-so-far + budgets)
          retrieve -> run queries, append evidence, loop again (multi-round retrieval)
          ask      -> return that ONE pruning question (turn ends; budget enforced)
          answer   -> compose reply from evidence (turn ends)
          escalate -> safety hand-off (turn ends)
      (if max_steps hit without a terminal action -> answer with what we have)

The loop only orchestrates; every LLM/retrieval touch goes through `reasoner`/`adapter`, so it
runs fully offline in tests. compose_* own all user-facing text and are told to hide internals.
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
        panel. Names + fact sentences only, never internal scores/IDs."""
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
            d["evidence"] = self.evidence_view()
            if include_trace:
                d["trace"] = [s.to_dict() for s in self.state.trace]
        return d


class TCMAgent:
    def __init__(self, reasoner, adapter: RetrievalAdapter, schema: SchemaSpec, max_steps: int = 6):
        self.reasoner = reasoner
        self.adapter = adapter
        self.schema = schema
        # Hard bound on controller iterations within one user turn -- a backstop so a
        # misbehaving controller can never spin forever even if the budgets don't bite.
        self.max_steps = max_steps

    @classmethod
    def build(cls, dataset=None, merge=None, max_ask_rounds=3) -> tuple["TCMAgent", AgentState]:
        from core.common import graph_dir
        from core.llm import LLMClient

        state = AgentState(max_ask_rounds=max_ask_rounds)
        if dataset:
            state.dataset = dataset
        if merge:
            state.merge = merge
        schema = load_schema_spec(state.dataset)
        wd = graph_dir(state.dataset, state.merge)
        client = LLMClient(wd / "llm_cache", provider="openai")
        from .reasoner import LLMReasoner
        reasoner = LLMReasoner(client)
        adapter = RetrievalAdapter(state.dataset, state.merge, schema,
                                   embedding_provider="openai")
        return cls(reasoner, adapter, schema), state

    # ---- the loop ----

    def run_turn(self, state: AgentState, user_message: str) -> TurnResult:
        state.add_user(user_message)
        state.new_turn()

        for _ in range(self.max_steps):
            d = stages.decide(state, self.reasoner, self.schema)
            action = d["action"]

            if action == "retrieve":
                stages.run_retrieval(state, self.adapter, d.get("queries"))
                continue  # loop back: controller sees the new evidence and decides again

            if action == "ask":
                return self._ask(state, d.get("question") or stages_default_ask())

            if action == "escalate":
                return self._escalate(state)

            # action == "answer" (or any fallback)
            return self._answer(state)

        # max_steps exhausted without a terminal action -> answer with what we have.
        return self._answer(state)

    # ---- terminal wrappers ----

    def _answer(self, state) -> TurnResult:
        text = stages.compose_answer(state, self.reasoner)
        state.add_assistant(text)
        state.end_episode()
        return TurnResult(action=Action.ANSWER, reply=text, state=state)

    def _ask(self, state, question: str) -> TurnResult:
        # The question text comes from the controller; ASK never costs an extra LLM call.
        state.ask_rounds += 1
        state.add_assistant(question)
        return TurnResult(action=Action.ASK, reply=question, state=state)

    def _escalate(self, state) -> TurnResult:
        text = stages.compose_escalate(state, self.reasoner)
        state.add_assistant(text)
        state.end_episode()
        return TurnResult(action=Action.ESCALATE, reply=text, state=state)


def stages_default_ask() -> str:
    """Fallback question if the controller chose ASK but left the question empty."""
    return "为了更好地帮您分析，能再具体说说主要的不适和伴随症状吗？"
