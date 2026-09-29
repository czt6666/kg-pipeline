"""merge/pipeline.py: end-to-end orchestration for multi-round extraction merge.

Consumes N already-extracted, already-validated round splits (see
scripts/extract_multiround.py) plus the source split's docs.jsonl (for source_text) --
never calls the LLM, so re-running after a rule change just re-reads disk.

Produces, under data/work/{dataset}/{out}/:
  docs.jsonl                  copied from the source split (source_text, for the UI)
  nodes.jsonl / edges.jsonl   same shape stage4_build_graph.py produces (entity_id,
                               doc_id, name, type, aliases, attributes / edge_id, doc_id,
                               head, relation, pid, tail, condition), plus merge-specific
                               fields (support, predicate_votes, conflicted, type_votes,
                               unanchored) -- so stage6_index.py / stage7_merge.py /
                               serve.py / the existing frontend all work unchanged.
  merge_metrics.json           Step 6 metrics (+ merge_metrics_diff.json if a previous
                               run for this split exists)
  review_unanchored.jsonl      nodes whose literal never anchored to source_text
  review_conflicted.jsonl      edges with more than one predicate vote
  alias_pairs_this_run.jsonl   alias pairs this run contributed to the global table
The global alias table itself persists at data/work/_merge_alias_table.json, shared
across every dataset/split this module is ever run on (Step 5: bootstrap once, reuse
everywhere).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import yaml  # noqa: E402
from common import read_jsonl, work_dir, write_jsonl  # noqa: E402

from merge.alias import AliasTable  # noqa: E402
from merge.anchor import anchor_entities_for_round  # noqa: E402
from merge.cluster import apply_alias_and_containment, build_clusters, cluster_mentions  # noqa: E402
from merge.edges import merge_edges_for_doc  # noqa: E402
from merge.metrics import compute_metrics, diff_against_previous, isolation_rate  # noqa: E402
from merge.types import Mention  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
GLOBAL_ALIAS_TABLE_PATH = REPO_ROOT / "data" / "work" / "_merge_alias_table.json"


def _load_type_priority(dataset: str) -> list[str]:
    schema = yaml.safe_load((REPO_ROOT / "schema" / f"{dataset.lower()}_schema.yaml").read_text())
    return [t["name"] if isinstance(t, dict) else t for t in schema["entity_types"]]


def _load_round_docs(dataset: str, round_splits: list[str]) -> dict:
    """Returns {doc_id: [{"round_idx": i, "entities": [...], "triples": [...]}]}."""
    by_doc = defaultdict(list)
    for i, split in enumerate(round_splits):
        wd = work_dir(dataset, split)
        for row in read_jsonl(wd / "extraction_valid.jsonl"):
            by_doc[row["doc_id"]].append({"round_idx": i, "entities": row["entities"], "triples": row["triples"]})
    return by_doc


def merge_document(doc_id: str, source_text: str, rounds: list[dict], alias_table: AliasTable,
                    type_priority: list[str]):
    """Merges however many rounds of one doc's (entities, triples) are passed in
    (usually all N, but the saturation curve / single-round baselines call this with
    fewer). Mutates alias_table with any newly-discovered pairs (Step 5). Returns
    (clusters, merged_edges, attributes_by_cluster)."""
    mentions: list[Mention] = []
    local_key_to_mention_idx = {}
    raw_edges = []

    for r in rounds:
        anchors = anchor_entities_for_round(source_text, r["entities"], r["triples"])
        for e in r["entities"]:
            a = anchors[e["local_id"]]
            idx = len(mentions)
            mentions.append(Mention(
                text=e["name"], entity_type=e["type"], round_idx=r["round_idx"],
                local_id=e["local_id"], char_span=a["span"], anchor_method=a["method"],
            ))
            local_key_to_mention_idx[(r["round_idx"], e["local_id"])] = idx
        for t in r["triples"]:
            if t.get("kind") == "intrinsic":
                continue  # folded into node attributes below, never an edge
            raw_edges.append({
                "round_idx": r["round_idx"], "head_local_id": t["head"], "tail_local_id": t["tail"],
                "predicate": t["relation"], "condition": t.get("condition"),
            })

    uf, idx = cluster_mentions(mentions)
    apply_alias_and_containment(uf, mentions, idx, alias_table.is_known_alias)
    clusters, mention_to_cluster = build_clusters(mentions, uf, idx, doc_id, type_priority)

    for c in clusters:
        for alias in c.aliases:
            alias_table.record(c.canonical, alias, c.node_type)

    merged_edges = merge_edges_for_doc(raw_edges, mention_to_cluster, local_key_to_mention_idx, doc_id)

    attributes_by_cluster = defaultdict(lambda: defaultdict(set))
    for r in rounds:
        for t in r["triples"]:
            if t.get("kind") != "intrinsic":
                continue
            hi = local_key_to_mention_idx.get((r["round_idx"], t["head"]))
            ti = local_key_to_mention_idx.get((r["round_idx"], t["tail"]))
            if hi is None or ti is None:
                continue
            attributes_by_cluster[mention_to_cluster[hi]][t["relation"]].add(mentions[ti].text)

    return clusters, merged_edges, attributes_by_cluster


def _merge_round_subset(docs_text: dict, by_doc: dict, round_indices: set[int],
                         type_priority: list[str], alias_table_seed: AliasTable):
    """Runs the per-doc merge restricted to a subset of rounds, starting every call from
    a *copy* of alias_table_seed so independent simulations (saturation curve points,
    single-round baselines) never leak state into each other or into the main run."""
    alias_table = alias_table_seed.snapshot()
    all_clusters, all_edges = [], []
    for doc_id, rounds in sorted(by_doc.items()):
        subset = [r for r in rounds if r["round_idx"] in round_indices]
        if not subset:
            continue
        clusters, edges, _ = merge_document(doc_id, docs_text.get(doc_id, ""), subset, alias_table, type_priority)
        all_clusters.extend(clusters)
        all_edges.extend(edges)
    return all_clusters, all_edges


def run(dataset: str, source_split: str, round_splits: list[str], out: str):
    type_priority = _load_type_priority(dataset)
    docs_text = {d["doc_id"]: d["text"] for d in read_jsonl(work_dir(dataset, source_split) / "docs.jsonl")}
    by_doc = _load_round_docs(dataset, round_splits)
    n_rounds = len(round_splits)

    alias_table = AliasTable(GLOBAL_ALIAS_TABLE_PATH)
    pre_run_snapshot = alias_table.snapshot()

    # ---- the actual deliverable: full N-round merge ----
    per_doc_clusters, per_doc_edges, per_doc_attrs = {}, {}, {}
    for doc_id, rounds in sorted(by_doc.items()):
        clusters, edges, attrs = merge_document(doc_id, docs_text.get(doc_id, ""), rounds, alias_table, type_priority)
        per_doc_clusters[doc_id] = clusters
        per_doc_edges[doc_id] = edges
        per_doc_attrs[doc_id] = attrs

    alias_pairs_this_run = alias_table.diff_since(pre_run_snapshot)
    alias_table.save()

    # ---- saturation curve: cumulative merge over round prefixes {0}, {0,1}, ... ----
    saturation = []
    prev_nodes = prev_edges = 0
    for k in range(1, n_rounds + 1):
        clusters, edges = _merge_round_subset(docs_text, by_doc, set(range(k)), type_priority, pre_run_snapshot)
        n_nodes, n_edges = len(clusters), len(edges)
        saturation.append({
            "round": k, "cum_nodes": n_nodes, "cum_edges": n_edges,
            "new_nodes": n_nodes - prev_nodes, "new_edges": n_edges - prev_edges,
        })
        prev_nodes, prev_edges = n_nodes, n_edges

    # ---- single-round baselines (each round alone, same pipeline) for compression ratio ----
    single_round_stats = []
    for r in range(n_rounds):
        clusters, edges = _merge_round_subset(docs_text, by_doc, {r}, type_priority, pre_run_snapshot)
        single_round_stats.append({
            "round": r, "n_nodes": len(clusters), "n_edges": len(edges),
            "isolation_rate": isolation_rate(clusters, edges),
        })

    merged_nodes_flat = [c for clist in per_doc_clusters.values() for c in clist]
    merged_edges_flat = [e for elist in per_doc_edges.values() for e in elist]

    metrics = compute_metrics(saturation, single_round_stats, merged_nodes_flat, merged_edges_flat)

    out_wd = work_dir(dataset, out)
    metrics_path = out_wd / "merge_metrics.json"
    diff = diff_against_previous(metrics, metrics_path)
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    if diff:
        (out_wd / "merge_metrics_diff.json").write_text(json.dumps(diff, ensure_ascii=False, indent=2))
    write_jsonl(out_wd / "alias_pairs_this_run.jsonl", alias_pairs_this_run)

    # ---- nodes.jsonl / edges.jsonl in stage4_build_graph.py's exact shape (+ extras) ----
    write_jsonl(out_wd / "docs.jsonl", read_jsonl(work_dir(dataset, source_split) / "docs.jsonl"))

    node_rows, edge_rows, unanchored_rows, conflicted_rows, mention_rows = [], [], [], [], []
    for doc_id, clusters in per_doc_clusters.items():
        attrs = per_doc_attrs[doc_id]
        for c in clusters:
            mention_ids = [f"{doc_id}#r{m.round_idx}#{m.local_id}" for m in c.provenance]
            row = {
                "entity_id": c.cluster_id, "doc_id": doc_id, "name": c.canonical, "type": c.node_type,
                "aliases": c.aliases,
                "attributes": {k: sorted(v) for k, v in attrs.get(c.cluster_id, {}).items()},
                "mention_ids": mention_ids,
                "support": c.support, "type_votes": c.type_votes, "unanchored": c.unanchored,
                "char_span": list(c.char_span) if c.char_span else None,
            }
            node_rows.append(row)
            if c.unanchored:
                unanchored_rows.append(row)
            # DocExtractionView.jsx highlights doc.text by slicing at each mention's
            # char_start/char_end and looks up the owning node via mention_ids -- this
            # is what makes "原文 <-> 图谱" correspondence clickable/hoverable for the
            # merged multi-round result, the same way it already works for a normal
            # single-round split's mentions.jsonl (stage2_validate.py's align_mentions).
            for mid, m in zip(mention_ids, c.provenance):
                mention_rows.append({
                    "mention_id": mid, "doc_id": doc_id,
                    "surface": m.text,
                    "char_start": m.char_span[0] if m.char_span else None,
                    "char_end": m.char_span[1] if m.char_span else None,
                    "align_method": m.anchor_method,
                    "round_idx": m.round_idx,
                })

    for doc_id, elist in per_doc_edges.items():
        for e in elist:
            row = {
                "edge_id": e.edge_id, "doc_id": doc_id, "head": e.subject_id, "relation": e.predicate,
                "pid": None, "tail": e.object_id, "condition": e.condition,
                "predicate_votes": e.predicate_votes, "condition_variants": e.condition_variants,
                "support": e.support, "conflicted": e.conflicted, "rounds": e.rounds,
            }
            edge_rows.append(row)
            if e.conflicted:
                conflicted_rows.append(row)

    write_jsonl(out_wd / "nodes.jsonl", node_rows)
    write_jsonl(out_wd / "edges.jsonl", edge_rows)
    write_jsonl(out_wd / "mentions.jsonl", mention_rows)
    write_jsonl(out_wd / "review_unanchored.jsonl", unanchored_rows)
    write_jsonl(out_wd / "review_conflicted.jsonl", conflicted_rows)

    print(f"nodes: {len(node_rows)}, edges: {len(edge_rows)}")
    print(f"unanchored nodes: {len(unanchored_rows)}/{len(node_rows)}, "
          f"conflicted edges: {len(conflicted_rows)}/{len(edge_rows)}")
    print(f"new/updated alias pairs this run: {len(alias_pairs_this_run)}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    if diff:
        print("--- diff vs previous run for this split ---")
        print(json.dumps(diff, ensure_ascii=False, indent=2))
    print(f"\nwrote {out_wd}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--source-split", required=True, help="split with docs.jsonl (source_text)")
    ap.add_argument("--round-splits", required=True, help="comma-separated round split names, in round order")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    run(args.dataset, args.source_split, args.round_splits.split(","), args.out)


if __name__ == "__main__":
    main()
