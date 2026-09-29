"""Graph Pattern search: directed, typed multi-hop queries seeded from a resolved entity.

Design doc (review it before touching PATTERNS_BY_TYPE): docs/retrieval_graph_patterns.md

Unlike `basic.graph_search` (unconstrained N-hop BFS for interactive exploration), every
pattern here is a fixed, named hop sequence chosen for a clinically meaningful question
shape ("疾病 --分型--> 证候 --治法--> 治法功效" etc). Two kinds:
  - profile_pattern(): always runs for any seed -- one-hop fan-out in both directions,
    grouped by relation, plus intrinsic attributes. The "entity card".
  - PATTERNS_BY_TYPE: named 1-4 hop chains, looked up by the seed's entity type. Only
    5 seed types have curated chains (疾病/证候/症状/中药/方剂); the other 4 schema types
    (病因/治法功效/性味/脏腑经络) are chain intermediates, not query entry points, and get
    profile-only coverage (see doc section 2.2).
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .graph_io import load_nodes_edges

MAX_FANOUT = 30
RECURSIVE_MAX_DEPTH = 2
# 鉴别/别名 are stored as a single directed edge for a logically symmetric fact ("A与B鉴别"
# is never also stored as "B与A鉴别") -- every lookup on these two relations must check both
# edge directions or a seed landing on the tail side would silently see nothing.
SYMMETRIC_RELATIONS = {"鉴别", "别名"}

PATTERNS_BY_TYPE = {
    "疾病": [
        {"id": "P-DISEASE-SYNDROMES", "chains": [
            [{"relations": ["分型"], "direction": "out"}],
        ]},
        {"id": "P-DISEASE-TREATMENT", "chains": [
            [{"relations": ["分型"], "direction": "out"}, {"relations": ["治法"], "direction": "out"}],
        ]},
        {"id": "P-DISEASE-FORMULAS", "chains": [
            [{"relations": ["分型"], "direction": "out"}, {"relations": ["方用"], "direction": "out"}],
        ]},
        {"id": "P-DISEASE-FULL-CHAIN", "chains": [
            [{"relations": ["分型"], "direction": "out"}, {"relations": ["方用"], "direction": "out"},
             {"relations": ["组成"], "direction": "out"}],
        ]},
        {"id": "P-DISEASE-ETIOLOGY",
         "recursive": {"relations": ["病因"], "direction": "out", "max_depth": RECURSIVE_MAX_DEPTH}},
        {"id": "P-DISEASE-LOCATION", "chains": [[{"relations": ["病位"], "direction": "out"}]]},
        {"id": "P-DISEASE-MAIN-SYMPTOMS", "chains": [[{"relations": ["主症", "兼症"], "direction": "out"}]]},
        {"id": "P-DISEASE-DIFFERENTIAL", "chains": [[{"relations": ["鉴别"], "direction": "out"}]]},
        {"id": "P-DISEASE-ALIAS", "chains": [[{"relations": ["别名"], "direction": "out"}]]},
    ],
    "证候": [
        {"id": "P-SYNDROME-PARENT", "chains": [[{"relations": ["分型"], "direction": "in"}]]},
        {"id": "P-SYNDROME-FULL-TX", "chains": [
            [{"relations": ["治法"], "direction": "out"}],
            [{"relations": ["方用"], "direction": "out"}, {"relations": ["组成"], "direction": "out"}],
            [{"relations": ["用药"], "direction": "out"}],
        ]},
        {"id": "P-SYNDROME-MODIFIERS", "chains": [
            [{"relations": ["加药", "减药", "加方", "换方"], "direction": "out"}],
        ], "recursive": {"relations": ["变证"], "direction": "out", "max_depth": RECURSIVE_MAX_DEPTH}},
        {"id": "P-SYNDROME-DIFFERENTIAL", "chains": [[{"relations": ["鉴别"], "direction": "out"}]]},
    ],
    "症状": [
        {"id": "P-SYMPTOM-TO-SYNDROME", "chains": [[{"relations": ["表现为"], "direction": "in"}]]},
        {"id": "P-SYMPTOM-TO-DISEASE", "chains": [
            [{"relations": ["表现为"], "direction": "in"}, {"relations": ["分型"], "direction": "in"}],
        ]},
        {"id": "P-SYMPTOM-AS-MAIN", "chains": [[{"relations": ["主症", "兼症"], "direction": "in"}]]},
        {"id": "P-SYMPTOM-AS-EFFECT", "chains": [[{"relations": ["病因"], "direction": "in"}]]},
        {"id": "P-SYMPTOM-TREATED-BY", "chains": [[{"relations": ["主治"], "direction": "in"}]]},
        # A symptom on its own has no 治法/方用 edge (those hang off 疾病/证候, see schema
        # domains) -- a plain query like "便秘"/"失眠" that resolves to a 症状 node otherwise
        # dead-ends at "which syndrome shows this" with no way to reach how it's treated.
        # Walk back up to the nearest 证候/疾病 that carries this symptom, then forward along
        # its regular treatment edges. `direction` is from the SEED's point of view: "in"
        # means the seed sits on the tail side of that relation (schema has 证候/疾病 as
        # head), so the first hop of every chain below walks backward to find "who shows
        # this symptom" before the second hop walks forward to "how do they treat it".
        {"id": "P-SYMPTOM-TREATMENT", "chains": [
            # 症状 <--表现为-- 证候 --治法--> 治法功效  (证候 directly shows this symptom, has its own 治法)
            [{"relations": ["表现为"], "direction": "in"}, {"relations": ["治法"], "direction": "out"}],
            # 症状 <--表现为-- 证候 --方用--> 方剂  (same 证候, via its prescribed formula instead)
            [{"relations": ["表现为"], "direction": "in"}, {"relations": ["方用"], "direction": "out"}],
            # 症状 <--主症/兼症-- 疾病 --分型--> 证候 --治法--> 治法功效  (症状 is a disease's headline
            # symptom rather than a syndrome's; go up to the disease, then down into one of its
            # syndrome subtypes to reach a 治法 edge)
            [{"relations": ["主症", "兼症"], "direction": "in"}, {"relations": ["分型"], "direction": "out"},
             {"relations": ["治法"], "direction": "out"}],
            # same as above, ending at the syndrome's 方用 formula instead of its 治法
            [{"relations": ["主症", "兼症"], "direction": "in"}, {"relations": ["分型"], "direction": "out"},
             {"relations": ["方用"], "direction": "out"}],
        ]},
    ],
    "中药": [
        {"id": "P-HERB-IN-FORMULA", "chains": [[{"relations": ["组成"], "direction": "in"}]]},
        {"id": "P-HERB-FOR-SYNDROME", "chains": [[{"relations": ["用药", "加药", "减药"], "direction": "in"}]]},
        {"id": "P-HERB-TO-DISEASE", "chains": [
            [{"relations": ["组成"], "direction": "in"}, {"relations": ["方用"], "direction": "in"},
             {"relations": ["分型"], "direction": "in"}],
        ]},
    ],
    "方剂": [
        {"id": "P-FORMULA-COMPOSITION", "chains": [[{"relations": ["组成"], "direction": "out"}]]},
        {"id": "P-FORMULA-INDICATION", "chains": [[{"relations": ["方用", "加方", "换方"], "direction": "in"}]]},
        {"id": "P-FORMULA-TO-DISEASE", "chains": [
            [{"relations": ["方用"], "direction": "in"}, {"relations": ["分型"], "direction": "in"}],
        ]},
    ],
}


def _build_adjacency(edges):
    """Full (not tuple-shorthand) adjacency in both directions, edge object retained so
    hops can carry `condition`/`edge_id` -- `basic._load_nodes_edges`'s adj is forward-only
    and drops the edge object, so it can't serve multi-hop reverse patterns or conditions."""
    fwd, rev = defaultdict(list), defaultdict(list)
    for e in edges:
        fwd[e["head"]].append((e["relation"], e["tail"], e))
        rev[e["tail"]].append((e["relation"], e["head"], e))
    return fwd, rev


def _hop(fwd, rev, node_id, relations, direction):
    """One hop from node_id along any relation in `relations`. `direction` is "out" (node_id
    is head) or "in" (node_id is tail); symmetric relations (鉴别/别名) always check both
    regardless of declared direction (see SYMMETRIC_RELATIONS). Returns up to MAX_FANOUT
    hop dicts {other, head, relation, tail, condition}, sorted by `other` for determinism."""
    relset = set(relations)
    symmetric = bool(relset & SYMMETRIC_RELATIONS)
    seen = set()
    out = []
    if direction == "out" or symmetric:
        for rel, tail, edge in fwd.get(node_id, []):
            if rel in relset and tail not in seen:
                seen.add(tail)
                out.append({"other": tail, "head": node_id, "relation": rel, "tail": tail,
                            "condition": edge.get("condition")})
    if direction == "in" or symmetric:
        for rel, head, edge in rev.get(node_id, []):
            if rel in relset and head not in seen:
                seen.add(head)
                out.append({"other": head, "head": head, "relation": rel, "tail": node_id,
                            "condition": edge.get("condition")})
    out.sort(key=lambda h: h["other"])
    return out[:MAX_FANOUT]


def _strip_internal(hop):
    return {k: v for k, v in hop.items() if k != "other"}


def _execute_chain(fwd, rev, seed_id, steps):
    """Walks a fixed step sequence from seed_id, branching at every hop. Returns a list of
    complete hop-lists, one per leaf reached (empty list if the first step has no hits)."""
    paths = [[]]
    for step in steps:
        next_paths = []
        for path in paths:
            frontier = path[-1]["other"] if path else seed_id
            for hop in _hop(fwd, rev, frontier, step["relations"], step["direction"]):
                next_paths.append(path + [hop])
        paths = next_paths
        if not paths:
            break
    return paths


def _execute_recursive(fwd, rev, seed_id, relations, direction, max_depth):
    """BFS-chases a single relation set up to max_depth hops, emitting a path for *every*
    depth reached (not just the deepest) -- e.g. a depth-1 母证候→子证候 hop and, if it
    exists, the depth-2 子证候→孙证候 extension are both returned as separate paths."""
    all_paths = []
    frontier_paths = [[]]
    for _ in range(max_depth):
        next_frontier = []
        for path in frontier_paths:
            frontier = path[-1]["other"] if path else seed_id
            for hop in _hop(fwd, rev, frontier, relations, direction):
                new_path = path + [hop]
                all_paths.append(new_path)
                next_frontier.append(new_path)
        frontier_paths = next_frontier
        if not frontier_paths:
            break
    return all_paths


def profile_pattern(nodes, fwd, rev, seed_id):
    """One-hop fan-out in both directions, grouped by relation, plus intrinsic attributes.
    Runs for any seed regardless of type -- see docs/retrieval_graph_patterns.md 2.1."""
    node = nodes.get(seed_id, {})
    out_edges, in_edges = defaultdict(list), defaultdict(list)
    for rel, tail, edge in fwd.get(seed_id, []):
        if len(out_edges[rel]) < MAX_FANOUT:
            out_edges[rel].append({"entity_id": tail, "condition": edge.get("condition")})
    for rel, head, edge in rev.get(seed_id, []):
        if len(in_edges[rel]) < MAX_FANOUT:
            in_edges[rel].append({"entity_id": head, "condition": edge.get("condition")})
    return {
        "seed_entity_id": seed_id,
        "attributes": node.get("attributes", {}),
        "out": dict(out_edges),
        "in": dict(in_edges),
    }


def graph_pattern_search(wd: Path, seed_id: str):
    """Returns {"profile": {...}, "patterns": [{pattern_id, hops, end_entity_id}, ...]}.
    `patterns` is empty (not an error) if the seed's type isn't one of the 5 curated entry
    types, or if none of its chains found anything."""
    nodes, edges = load_nodes_edges(wd)
    fwd, rev = _build_adjacency(edges)

    profile = profile_pattern(nodes, fwd, rev, seed_id)

    seed_type = nodes.get(seed_id, {}).get("type")
    results = []
    for pattern in PATTERNS_BY_TYPE.get(seed_type, []):
        paths = []
        for chain in pattern.get("chains", []):
            paths.extend(_execute_chain(fwd, rev, seed_id, chain))
        if "recursive" in pattern:
            r = pattern["recursive"]
            paths.extend(_execute_recursive(fwd, rev, seed_id, r["relations"], r["direction"], r["max_depth"]))
        for path in paths:
            results.append({
                "pattern_id": pattern["id"],
                "seed_entity_id": seed_id,
                "hops": [_strip_internal(h) for h in path],
                "end_entity_id": path[-1]["other"],
            })

    return {"profile": profile, "patterns": results}
