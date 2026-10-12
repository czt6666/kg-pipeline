"""Shared data types for the multi-round extraction merge module (see merge/pipeline.py
for the end-to-end flow). Plain dataclasses so every intermediate result is trivially
JSON-serializable via dataclasses.asdict() -- nothing here holds a live reference to a
round's raw LLM response; merge/ only ever reads already-validated extraction_valid.jsonl.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Triple:
    """One subject-predicate-object fact from a single extraction round, already
    schema-validated (domain/range enforced, flip applied) by stage2_validate.py --
    same triple shape the task spec declares, resolved from local_id references to
    literal subject/object text+type."""
    subject: str
    subject_type: str
    predicate: str
    object: str
    object_type: str
    condition: str | None = None


@dataclass
class Mention:
    """One entity literal as it appeared in one round, plus where it anchors in the
    source chunk text (see merge/anchor.py)."""
    text: str
    entity_type: str
    round_idx: int
    local_id: str
    char_span: tuple[int, int] | None
    anchor_method: str  # "exact" | "prefix" | "unanchored"


@dataclass
class NodeCluster:
    cluster_id: str
    canonical: str
    aliases: list[str]
    node_type: str
    type_votes: dict[str, int]
    char_span: tuple[int, int] | None
    support: int
    provenance: list[Mention] = field(default_factory=list)
    unanchored: bool = False


@dataclass
class MergedEdge:
    edge_id: str
    subject_id: str
    object_id: str
    predicate: str
    predicate_votes: dict[str, int]
    condition: str | None
    condition_variants: list[str]
    support: int
    conflicted: bool
    rounds: list[int] = field(default_factory=list)


@dataclass
class AliasPair:
    canonical: str
    alias: str
    entity_type: str
    support: int
