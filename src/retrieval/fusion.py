"""Hybrid ranking: fuses lexical + semantic + a graph-connectivity prior into one ranked
list of candidate entities, using weighted Reciprocal Rank Fusion (RRF).

RRF (`score = sum(weight / (k + rank))`, `k=60` is the standard default from the original
TREC paper) is the starting point rather than e.g. a learned/calibrated blend because the
three channels' raw scores live on incomparable scales -- difflib ratio, faiss cosine, and
a raw node degree count can't be averaged directly, but their *rank order* can always be
combined. Weights are keyword args so `eval/run_hybrid.py` can sweep them once there's a
baseline to tune against (see plan: "你先自己测试自己调试...之后我会协助你调优").

The "graph" channel here is a plausibility prior, not a full pattern search: ranking
candidate entities by connectivity in the graph they'd need `graph_pattern_search` run on,
which requires a resolved entity first, would be circular. Degree is a cheap proxy that
also directly counters a real problem seen in manual testing -- junk single-character
nodes from older/buggy extraction runs (e.g. a lone "证" node) can win on substring/fuzzy
lexical score, but have near-zero degree, so they naturally sink here instead of being
returned as the top "match".
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from common import read_jsonl

RRF_K = 60

# Additive, not multiplicative: RRF scores over ~10-20 candidates with these weights land
# well under 0.05 (see docstring below for the observed case that motivated this), so a
# +1.0 / +0.5 boost guarantees exact/证-suffix-variant lexical matches always outrank
# everything else, while ties among several exact matches (e.g. a term extracted as three
# different types across documents pre-dating this session's 证-suffix normalization work)
# still fall back to their RRF score for ordering.
EXACT_TIER_BOOST = {
    "exact": 1.0, "exact_zheng_variant": 0.5,
    "exact_alias": 0.3, "exact_alias_zheng_variant": 0.2,
}
# Priority order for fuse_candidates' tier restriction below -- an exact hit on a node's own
# *name* always beats an exact hit that only matched through an (looser, promotion-derived)
# alias, regardless of relative RRF/boost scores.
EXACT_TIER_PRIORITY = ("exact", "exact_zheng_variant", "exact_alias", "exact_alias_zheng_variant")


def node_degree(wd: Path) -> Counter:
    """entity_id -> total edge count (head or tail), used as the graph-prior channel."""
    degree = Counter()
    for e in read_jsonl(wd / "edges.jsonl"):
        degree[e["head"]] += 1
        degree[e["tail"]] += 1
    return degree


def reciprocal_rank_fusion(ranked_lists: list[list[str]], weights: list[float], k: int = RRF_K):
    """ranked_lists[i] is a list of entity_ids best-first; weights[i] is that channel's
    weight. Returns {entity_id: fused_score}, higher is better. An entity absent from a
    channel's list simply doesn't get that channel's term (not penalized beyond missing
    the bonus) -- standard RRF behavior."""
    scores = defaultdict(float)
    for ranked, weight in zip(ranked_lists, weights):
        for rank, entity_id in enumerate(ranked):
            scores[entity_id] += weight / (k + rank + 1)
    return dict(scores)


def fuse_candidates(lexical_hits, semantic_hits, degree: Counter, top_k: int = 10,
                     w_lexical: float = 1.0, w_semantic: float = 1.0, w_graph: float = 0.5):
    """Fuses lexical_search/semantic_search hit lists (each already sorted best-first) plus
    a graph-degree prior into one ranked candidate list. `w_graph` defaults lower than the
    other two since it's a plausibility tie-breaker, not a relevance signal on its own --
    a high-degree node that neither lexical nor semantic surfaced at all should not outrank
    one they both agree on.

    A plain RRF sum understates a genuine exact-name match: e.g. querying "麻黄汤" (a real
    formula, exact lexical hit) initially ranked it *below* five "麻黄"-adjacent herbs/
    formulas that merely showed up in both the lexical substring tier and the semantic
    top-10 -- the embedding space clusters all "麻黄*"-named entities close together, so
    "麻黄汤" itself didn't even make the semantic top-10, and RRF's presence-across-channels
    scoring let entities that were mediocre-but-consistent outweigh one channel's certainty.
    `EXACT_TIER_BOOST` fixes this: exact/证-suffix-variant lexical matches get an additive
    boost that dominates the RRF sum, so they always rank first regardless of semantic/graph
    signal (found via manual testing during development, see retrieval_debug.py output).

    Returns [{entity_id, name, type, fused_score, channels: {lexical, semantic, degree}}, ...]
    sorted by fused_score descending -- `channels` is kept for debugging/tuning, not hidden.
    """
    by_id = {}
    lex_tier_by_id = {}
    for h in lexical_hits:
        by_id[h["entity_id"]] = {"name": h["name"], "type": h["type"]}
        lex_tier_by_id[h["entity_id"]] = h.get("tier")
    for h in semantic_hits:
        by_id.setdefault(h["entity_id"], {"name": h.get("name"), "type": h.get("type")})

    lex_order = [h["entity_id"] for h in lexical_hits]
    sem_order = [h["entity_id"] for h in semantic_hits]
    # graph channel only ranks entities the other two already surfaced -- it's a prior over
    # candidates, not an independent recall path (a term with zero lexical/semantic hits
    # shouldn't suddenly surface the highest-degree node in the whole graph).
    candidate_ids = set(lex_order) | set(sem_order)
    graph_order = sorted(candidate_ids, key=lambda eid: -degree.get(eid, 0))

    fused = reciprocal_rank_fusion([lex_order, sem_order, graph_order],
                                    [w_lexical, w_semantic, w_graph])

    lex_rank = {eid: r for r, eid in enumerate(lex_order)}
    sem_rank = {eid: r for r, eid in enumerate(sem_order)}
    deg_rank = {eid: r for r, eid in enumerate(graph_order)}

    out = []
    for entity_id, score in fused.items():
        info = by_id.get(entity_id, {})
        tier = lex_tier_by_id.get(entity_id)
        boosted = score + EXACT_TIER_BOOST.get(tier, 0.0)
        out.append({
            "entity_id": entity_id, "name": info.get("name"), "type": info.get("type"),
            "fused_score": boosted, "lexical_tier": tier,
            "channels": {
                "lexical_rank": lex_rank.get(entity_id),
                "semantic_rank": sem_rank.get(entity_id),
                "degree_rank": deg_rank.get(entity_id),
                "degree": degree.get(entity_id, 0),
            },
        })
    out.sort(key=lambda e: -e["fused_score"])

    # An exact (or 证-suffix-variant) name match is unambiguous -- once one exists, lower
    # tiers are noise, not real alternatives, for a caller that "passes a precise TCM term"
    # per this module's contract. e.g. querying "感冒" should come back as just the 感冒/疾病
    # node, not diluted with every other disease that happens to have "感冒" promoted onto
    # its alias list (虚体感冒/时行感冒/... -- see lexical.py's docstring) or that merely
    # contains/fuzzy-resembles "感冒". Only trims within the *best* tier present, so
    # genuinely ambiguous exact matches (e.g. a term extracted as two different types under
    # its own name) still list both.
    for tier in EXACT_TIER_PRIORITY:
        at_tier = [e for e in out if e["lexical_tier"] == tier]
        if at_tier:
            return at_tier[:top_k]
    return out[:top_k]


# Relations whose target is "how do we act on this" (a treatment method, formula, herb, or
# a formula's composition/indication) rather than mere classification/reference info. Used
# below to keep e.g. a hub symptom's dozen "which other diseases also show this" facts from
# starving out the one or two facts that actually answer "how is this treated" at the same
# hop depth (real usage feedback: searching 失眠/便秘 came back with no treatment info even
# though the graph has it, because rank_facts' old tie-break was pattern_id alone).
TREATMENT_RELATIONS = {"治法", "方用", "组成", "用药", "加药", "减药", "加方", "换方", "主治"}


def rank_facts(patterns: list[dict], top_k: int = 20):
    """Orders graph-pattern hits for display: fewer hops first (more directly relevant to
    the seed), then treatment-relevant chains (see TREATMENT_RELATIONS) ahead of purely
    classificatory ones at the same hop count, then by pattern_id/end_entity_id for
    determinism.

    Drops single-hop paths: every compound pattern's 1-hop chain is, by construction, a
    strict subset of the profile pattern's one-hop fan-out (same edges, just grouped by a
    named pattern instead of by raw relation) -- keeping them here would print the same
    fact twice (once from the profile, once as e.g. "P-DISEASE-MAIN-SYMPTOMS"). Multi-hop
    patterns (P-SYMPTOM-TO-SYNDROME's disease-reverse extension, full treatment chains,
    etc.) surface information the profile can't, so those are kept.
    """
    multi_hop = [p for p in patterns if len(p["hops"]) > 1]
    def sort_key(p):
        is_non_treatment = p["hops"][-1]["relation"] not in TREATMENT_RELATIONS
        return (len(p["hops"]), is_non_treatment, p["pattern_id"], p["end_entity_id"])
    ranked = sorted(multi_hop, key=sort_key)
    return ranked[:top_k]
