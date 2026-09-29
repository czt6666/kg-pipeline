"""Step 4 of merge/: edge merging across rounds, for one document's clustered node
graph. Existence (4a) unions across rounds; predicate labels (4b) vote instead of
union, because two different predicates on the same (subject, object) pair are
competing hypotheses, not complementary facts. Condition (4d) is part of the edge
identity (fuzzy-matched, never ignored) -- see _condition_match.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict

from .types import MergedEdge

# schema/tcm_schema.yaml declares a flat, closed relation set -- no parent/child
# hierarchy metadata exists (task spec Step 4c: "如果 schema 中谓词是扁平的封闭集合，
# 就跳过这条规则，一律投票"). Left as an explicit hook: if a future schema adds
# hierarchy info (e.g. {"君药": "组成"}), populate this dict and _resolve_predicate will
# keep the more specific child instead of flagging a conflict.
RELATION_HIERARCHY: dict[str, str] = {}


def normalize_condition(s: str | None) -> str | None:
    if not s:
        return None
    s = unicodedata.normalize("NFKC", s).strip()
    s = re.sub(r"\s+", "", s)
    return s or None


def _condition_match(a: str | None, b: str | None) -> bool:
    """Conditions must match at LEAST this loosely to be considered "the same trigger" --
    exact equality after normalization, or one containing the other (wording varies
    round to round, e.g. "若阴虚火旺" vs "若阴虚火旺，胃火上炎"). Two None conditions
    match each other (both "unconditional"); a None never matches a real condition."""
    if a is None or b is None:
        return a is b
    return a == b or a in b or b in a


def _resolve_predicate(votes: Counter) -> tuple[str, bool]:
    """Returns (chosen_predicate, conflicted). Majority vote; ties broken by first-seen
    order (Counter preserves insertion order, which follows round order -- deterministic
    given a fixed round-split order). conflicted=True whenever more than one distinct
    predicate label was observed for this edge identity, tie or not -- that's the signal
    metrics.py turns into the predicate-conflict-rate diagnostic."""
    labels = list(votes.keys())
    if len(labels) == 1:
        return labels[0], False

    if RELATION_HIERARCHY:
        children = [l for l in labels if RELATION_HIERARCHY.get(l) in labels]
        parents_covered = {RELATION_HIERARCHY.get(l) for l in children}
        if children and set(labels) <= (set(children) | parents_covered):
            return max(children, key=lambda l: votes[l]), False

    top = max(votes.values())
    tied = [l for l in labels if votes[l] == top]
    return tied[0], True


def merge_edges_for_doc(raw_edges: list[dict], mention_to_cluster: dict, local_key_to_mention_idx: dict,
                         doc_id: str) -> list[MergedEdge]:
    """raw_edges: [{round_idx, head_local_id, tail_local_id, predicate, condition}], all
    relational (intrinsic triples are handled separately in pipeline.py as node
    attributes, never as edges)."""
    pair_buckets: dict[tuple[str, str], list] = defaultdict(list)
    for e in raw_edges:
        hi = local_key_to_mention_idx.get((e["round_idx"], e["head_local_id"]))
        ti = local_key_to_mention_idx.get((e["round_idx"], e["tail_local_id"]))
        if hi is None or ti is None:
            continue
        pair_buckets[(mention_to_cluster[hi], mention_to_cluster[ti])].append(e)

    merged, n = [], 0
    for (h_cluster, t_cluster), edges in sorted(pair_buckets.items()):
        # Split this node-pair's edges into condition buckets -- greedy first-fit
        # against already-open buckets, in raw_edges' (deterministic) order. This is
        # what makes condition part of the dedup key (4d): edges triggered under
        # genuinely different conditions never get merged into one, no matter how many
        # rounds each side has.
        cond_buckets: list[dict] = []
        for e in edges:
            cond = normalize_condition(e.get("condition"))
            slot = next((b for b in cond_buckets if _condition_match(b["repr"], cond)), None)
            if slot is None:
                slot = {"repr": cond, "members": []}
                cond_buckets.append(slot)
            elif cond and (slot["repr"] is None or len(cond) > len(slot["repr"])):
                slot["repr"] = cond  # prefer the more detailed condition text as representative
            slot["members"].append(e)

        for b in cond_buckets:
            votes = Counter(m["predicate"] for m in b["members"])
            predicate, conflicted = _resolve_predicate(votes)
            support = len({m["round_idx"] for m in b["members"]})
            condition_variants = sorted({normalize_condition(m.get("condition")) for m in b["members"]
                                          if normalize_condition(m.get("condition"))})
            merged.append(MergedEdge(
                edge_id=f"{doc_id}#e{n}",
                subject_id=h_cluster, object_id=t_cluster,
                predicate=predicate, predicate_votes=dict(votes),
                condition=b["repr"], condition_variants=condition_variants,
                support=support, conflicted=conflicted,
                rounds=sorted({m["round_idx"] for m in b["members"]}),
            ))
            n += 1
    return merged
