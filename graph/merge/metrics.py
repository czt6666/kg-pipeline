"""Step 6 of merge/: metrics that distinguish real recall gain from "the same entity
counted N times" (see task spec Section 5 -- all three failure modes make the graph
*bigger*, so raw node/edge counts alone cannot tell them apart from a healthy merge).
"""
from __future__ import annotations

import json
from pathlib import Path


def isolation_rate(clusters: list, edges: list) -> float:
    if not clusters:
        return 0.0
    connected = set()
    for e in edges:
        connected.add(e.subject_id)
        connected.add(e.object_id)
    ids = {c.cluster_id for c in clusters}
    return len(ids - connected) / len(ids)


def compute_metrics(saturation: list[dict], single_round_stats: list[dict],
                     merged_nodes: list, merged_edges: list) -> dict:
    avg_single_nodes = sum(s["n_nodes"] for s in single_round_stats) / len(single_round_stats)
    avg_single_isolation = sum(s["isolation_rate"] for s in single_round_stats) / len(single_round_stats)

    n_edges = len(merged_edges)
    n_conflicted = sum(1 for e in merged_edges if e.conflicted)
    n_support1 = sum(1 for e in merged_edges if e.support == 1)
    n_unanchored = sum(1 for n in merged_nodes if n.unanchored)

    return {
        "n_rounds": len(single_round_stats),
        "saturation": saturation,
        "single_round_stats": single_round_stats,
        "avg_single_round_nodes": avg_single_nodes,
        "merged_nodes": len(merged_nodes),
        "compression_ratio": (len(merged_nodes) / avg_single_nodes) if avg_single_nodes else None,
        "n_edges": n_edges,
        "n_conflicted_edges": n_conflicted,
        "predicate_conflict_rate": (n_conflicted / n_edges) if n_edges else None,
        "isolation_rate_single_avg": avg_single_isolation,
        "isolation_rate_merged": isolation_rate(merged_nodes, merged_edges),
        "single_round_only_edge_ratio": (n_support1 / n_edges) if n_edges else None,
        "n_unanchored_nodes": n_unanchored,
        "n_nodes": len(merged_nodes),
    }


def diff_against_previous(current: dict, previous_path: Path) -> dict | None:
    """All headline numbers must be read as a diff against the last run, not in
    isolation (task spec: "有意义的永远是改了配置之后哪个指标动了、往哪动"). Returns
    None if there's nothing to diff against yet (first run for this split)."""
    if not previous_path.exists():
        return None
    previous = json.loads(previous_path.read_text())
    diff = {}
    for k, v in current.items():
        if not isinstance(v, (int, float)):
            continue
        pv = previous.get(k)
        if isinstance(pv, (int, float)):
            diff[k] = {"previous": pv, "current": v, "delta": v - pv}
    return diff
