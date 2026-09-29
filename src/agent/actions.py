"""Action schema for the agent loop.

Five terminal/step actions the decision stage may choose:
  ASK       -- information the *user* must supply is missing; ask one focused question.
  RETRIEVE  -- knowledge is missing but retrievable; emit a RetrievalRequest for the
               hybrid retrieval module (the agent never queries the graph itself).
  ANSWER    -- enough is known (from dialogue + evidence) to answer now.
  TRIAGE    -- goal is symptom triage / orientation (which direction of care, urgency),
               not a knowledge question. (Department/doctor recommendation: future.)
  ESCALATE  -- higher risk or clearly needs in-person professional judgement; hand off.

RetrievalRequest is what the agent produces; Evidence is what comes back. Both are plain
dataclasses (JSON-serialisable) so a request/response pair is fully inspectable in the trace.
The RetrievalRequest `path` is validated against schema_spec before execution -- the agent
cannot invent relations or walk impossible chains.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Action(str, Enum):
    ASK = "ASK"
    RETRIEVE = "RETRIEVE"
    ANSWER = "ANSWER"
    TRIAGE = "TRIAGE"
    ESCALATE = "ESCALATE"


@dataclass
class RetrievalQuery:
    """One entity to resolve + the schema relation path to follow from it. `path` uses
    schema relation names only (validated by schema_spec.validate_path); it prioritises
    which of the resolved entity's facts matter, it does not invent graph traversal."""

    term: str
    seed_type: str | None = None  # expected type of `term`, for validation + disambiguation
    path: list[str] = field(default_factory=list)
    focus: str = ""  # free-text note on why this query (treatment / symptoms / composition ...)

    def to_dict(self) -> dict:
        return {"term": self.term, "seed_type": self.seed_type, "path": self.path, "focus": self.focus}


@dataclass
class RetrievalRequest:
    queries: list[RetrievalQuery]
    top_k: int = 10
    rationale: str = ""

    def to_dict(self) -> dict:
        return {"queries": [q.to_dict() for q in self.queries], "top_k": self.top_k, "rationale": self.rationale}

    def signature(self) -> str:
        """Stable key for dedup -- so the loop doesn't re-issue an identical request."""
        return "|".join(sorted(f"{q.term}:{q.seed_type}:{'>'.join(q.path)}" for q in self.queries))


@dataclass
class EvidenceFact:
    sentence: str
    source: str  # pattern_id or "profile"
    relations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"sentence": self.sentence, "source": self.source, "relations": self.relations}


@dataclass
class Evidence:
    """Normalised result of one RetrievalQuery against the hybrid retrieval module."""

    query: str
    found: bool
    resolved_entity: dict | None = None  # {entity_id, name, type}
    candidates: list[str] = field(default_factory=list)  # alternative names, for disambiguation
    facts: list[EvidenceFact] = field(default_factory=list)
    summary: str | None = None
    note: str = ""  # e.g. "未找到匹配实体" / "解析到的实体类型与预期不符"

    def as_text(self) -> str:
        if not self.found:
            return f"[检索「{self.query}」]：未找到匹配的知识图谱实体。"
        head = self.resolved_entity or {}
        lines = [f"[检索「{self.query}」→ 命中『{head.get('name')}』（{head.get('type')}）]"]
        if self.candidates:
            lines.append("  其他候选：" + "、".join(self.candidates))
        for f in self.facts:
            lines.append(f"  - {f.sentence}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "found": self.found,
            "resolved_entity": self.resolved_entity,
            "candidates": self.candidates,
            "facts": [f.to_dict() for f in self.facts],
            "summary": self.summary,
            "note": self.note,
        }
