"""Agent State: the single object threaded through the loop.

Everything the agent knows about the current conversation lives here -- the raw dialogue,
the latest per-stage structured judgements, accumulated retrieval Evidence, loop counters,
and a step-by-step `trace` for observability. It is a plain dataclass with a `to_dict()`
so a whole run can be dumped to JSON and replayed/inspected offline; no database, no ORM.

`conversation` is the only thing shown to the user (assistant turns). Everything else
(understanding = latest controller decision, candidates, evidence, trace) is internal and must
never leak into a final answer -- see prompts.answer_prompt / stages.compose_answer.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .actions import Evidence, RetrievalRequest

DEFAULT_DATASET = "TCM"
# The combined 3-book graph (neike + jichu + zhenduan) -- widest coverage for knowledge QA.
DEFAULT_MERGE = "merged_tcm_all_v4_pro_3round"


@dataclass
class TraceStep:
    """One observable unit of work. `output` is the stage's structured result (already
    JSON-serialisable); `meta` holds latency/model/etc. Never rendered to the user."""

    step: int
    stage: str
    output: Any
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"step": self.step, "stage": self.stage, "output": self.output, "meta": self.meta}


@dataclass
class AgentState:
    dataset: str = DEFAULT_DATASET
    merge: str = DEFAULT_MERGE
    # Bounds RETRIEVE rounds *within a single user turn* -- prevents infinite retrieve loops
    # while still allowing "retrieve, judge insufficient, retrieve again" a couple of times.
    max_retrieval_rounds: int = 3

    # How many grounded discriminating questions we'll ask in one consult episode before
    # forcing an answer -- the hard cap that kills the endless-ASK failure mode.
    max_ask_rounds: int = 3

    conversation: list[dict] = field(default_factory=list)  # [{role, content}]
    understanding: dict | None = None  # `interpret` output: mode / symptoms / focus / entities
    risk: dict | None = None
    evidence: list[Evidence] = field(default_factory=list)
    retrieval_history: list[RetrievalRequest] = field(default_factory=list)
    # The controller's latest candidate 证候 -- the branches that questioning prunes. Surfaced
    # to the UI's 候选证候 chips; symptoms are not tracked separately (the controller reads them
    # straight off the transcript each step).
    candidates: list[dict] = field(default_factory=list)
    # Persists across turns within a consult episode (each ASK is its own turn); reset when
    # the episode ends (ANSWER/TRIAGE/ESCALATE).
    ask_rounds: int = 0

    # per-turn scratch (reset at the top of each user turn)
    retrieval_rounds: int = 0
    trace: list[TraceStep] = field(default_factory=list)
    _step: int = 0

    # Optional progress sink for streaming a turn to the client: called with
    # (event_type, payload) for every trace step ("step") and answer text chunk ("delta").
    on_event: Callable[[str, dict], None] | None = field(default=None, repr=False)

    # ---- conversation helpers ----

    def add_user(self, text: str):
        self.conversation.append({"role": "user", "content": text})

    def add_assistant(self, text: str):
        self.conversation.append({"role": "assistant", "content": text})

    def transcript(self, max_turns: int = 12) -> str:
        turns = self.conversation[-max_turns:]
        role_cn = {"user": "用户", "assistant": "助手"}
        return "\n".join(f"{role_cn.get(t['role'], t['role'])}：{t['content']}" for t in turns)

    def latest_user(self) -> str:
        for t in reversed(self.conversation):
            if t["role"] == "user":
                return t["content"]
        return ""

    # ---- evidence helpers ----

    def evidence_block(self) -> str:
        """All accumulated evidence rendered as plain fact bullets -- the grounding material
        for judge/answer stages. Empty string when nothing retrieved yet."""
        if not self.evidence:
            return ""
        blocks = []
        for ev in self.evidence:
            blocks.append(ev.as_text())
        return "\n\n".join(blocks)

    def new_turn(self):
        """Reset per-turn scratch. Evidence is rebuilt fresh each turn (the consult path
        re-retrieves the full cumulative symptom set every turn, so keeping the previous
        turn's evidence would just pile up duplicates and bloat the differential prompt);
        symptoms/understanding persist and are re-derived from the transcript."""
        self.retrieval_rounds = 0
        self.evidence = []

    def end_episode(self):
        """Called when a turn terminates in a final answer/triage/escalate: the consult
        episode is over, so the ask budget resets for whatever the user asks next."""
        self.ask_rounds = 0

    # ---- observability ----

    def log(self, stage: str, output: Any, **meta) -> TraceStep:
        self._step += 1
        s = TraceStep(step=self._step, stage=stage, output=output, meta=meta)
        self.trace.append(s)
        self.emit("step", s.to_dict())
        return s

    def emit(self, event: str, payload: dict):
        if self.on_event:
            self.on_event(event, payload)

    def text_sink(self):
        """on_text callback for reasoner.write that forwards answer chunks as "delta"
        events, or None when nobody is listening (so the LLM call stays non-streaming)."""
        if not self.on_event:
            return None
        return lambda chunk: self.emit("delta", {"text": chunk})

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "merge": self.merge,
            "conversation": self.conversation,
            "understanding": self.understanding,
            "risk": self.risk,
            "candidates": self.candidates,
            "evidence": [e.to_dict() for e in self.evidence],
            "retrieval_history": [r.to_dict() for r in self.retrieval_history],
            "trace": [s.to_dict() for s in self.trace],
        }


def timed():
    """tiny helper: returns a callable that yields elapsed ms since creation."""
    t0 = time.time()
    return lambda: int((time.time() - t0) * 1000)
