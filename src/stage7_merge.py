"""Stage 7: cross-document merge into one complete KG per dataset.

Merges every split that already has nodes.jsonl (docred -> eval200; genwiki -> test)
into a single graph under data/work/{dataset}/merged/.

Cross-document alignment reuses the SAME normalized-name + type key as intra-document
alignment (stage3_align.normalize_name): NFKC + whitespace collapse + article strip +
quote/hyphen unification + lowercase. Same-named, same-typed entities across different
documents become one node. This is a safe approximation for the Wikipedia-entity
datasets used here; the rare "two different John Smith" collision is accepted.

Outputs (in merged/):
  nodes.jsonl  {entity_id:"m#N", name(longest), type, aliases(all surfaces),
                attributes(merged), source_doc_ids(sorted), mention_ids(aggregated)}
  edges.jsonl  {edge_id, head, relation, pid, tail, source_doc_ids}  -- dedup by
                (head, relation, tail); source_doc_ids lists every doc supporting it.
  docs.jsonl   union of source-split docs (dedup by doc_id) plus a "split" field recording
               which split each doc came from, for provenance snippets and doc drill-down.
  stats.json   node/edge/type/relation counts.
  index/nodes.faiss + nodes.index_map.json  -- FAISS index over merged nodes for
                semantic search (reuses stage6_index.node_descriptions/build_index).
"""
import argparse
import json
from collections import defaultdict

from common import REPO_ROOT, read_jsonl, work_dir, write_jsonl
from llm_client import LLMClient
from stage3_align import UnionFind, normalize_name
from stage6_index import build_index, node_descriptions


def collect_splits(dataset: str) -> list[str]:
    """Splits under data/work/{dataset}/ with a finished nodes.jsonl AND full extraction
    coverage (>=80% of docs have an extraction_valid record). This excludes half-baked
    splits like docred/dev (998 docs, only ~10 extracted)."""
    base = REPO_ROOT / "data" / "work" / dataset
    out = []
    if base.exists():
        for d in sorted(base.iterdir()):
            if not d.is_dir() or d.name == "merged" or not (d / "nodes.jsonl").exists():
                continue
            n_docs = sum(1 for _ in read_jsonl(d / "docs.jsonl"))
            n_valid = sum(1 for _ in read_jsonl(d / "extraction_valid.jsonl"))
            if n_docs and n_valid / n_docs >= 0.8:
                out.append(d.name)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="docred")
    args = ap.parse_args()

    splits = collect_splits(args.dataset)
    if not splits:
        print(f"[{args.dataset}] no splits with nodes.jsonl found; nothing to merge.")
        return
    print(f"[{args.dataset}] merging splits: {splits}")

    wd = work_dir(args.dataset, "merged")

    all_nodes, all_edges = [], []
    docs_by_id = {}
    for split in splits:
        swd = work_dir(args.dataset, split)
        for n in read_jsonl(swd / "nodes.jsonl"):
            all_nodes.append(n)
        for e in read_jsonl(swd / "edges.jsonl"):
            all_edges.append(e)
        for d in read_jsonl(swd / "docs.jsonl"):
            docs_by_id.setdefault(d["doc_id"], {**d, "split": split})

    # cross-doc union-find on (normalized name, type)
    uf = UnionFind([n["entity_id"] for n in all_nodes])
    groups = defaultdict(list)
    for n in all_nodes:
        groups[(normalize_name(n["name"]), n["type"])].append(n["entity_id"])
    for _, members in groups.items():
        for m in members[1:]:
            uf.union(members[0], m)

    root_to_members = defaultdict(list)
    for n in all_nodes:
        root_to_members[uf.find(n["entity_id"])].append(n)

    merged_nodes, old_to_new = [], {}
    for i, (root, members) in enumerate(
        sorted(root_to_members.items(), key=lambda kv: -len(kv[1]))
    ):
        new_id = f"m#{i}"
        for m in members:
            old_to_new[m["entity_id"]] = new_id
        canonical = max(members, key=lambda n: len(n["name"]))
        surfaces = {s for m in members for s in ([m["name"]] + list(m.get("aliases") or []))}
        aliases = sorted(surfaces - {canonical["name"]})
        attributes = defaultdict(list)
        mention_ids = []
        for m in members:
            mention_ids.extend(m.get("mention_ids") or [])
            for rel, vals in (m.get("attributes") or {}).items():
                for v in vals:
                    if v not in attributes[rel]:
                        attributes[rel].append(v)
        merged_nodes.append({
            "entity_id": new_id,
            "name": canonical["name"],
            "type": canonical["type"],
            "aliases": aliases,
            "attributes": dict(attributes),
            "source_doc_ids": sorted({m["doc_id"] for m in members}),
            "mention_ids": mention_ids,
        })

    edge_sources, edge_pid = defaultdict(set), {}
    for e in all_edges:
        h, t = old_to_new.get(e["head"]), old_to_new.get(e["tail"])
        if h is None or t is None:
            continue
        key = (h, e["relation"], t)
        edge_sources[key].add(e["doc_id"])
        edge_pid.setdefault(key, e.get("pid"))
    merged_edges = [
        {
            "edge_id": f"m#e{i}", "head": h, "relation": rel, "pid": edge_pid[key],
            "tail": t, "source_doc_ids": sorted(srcs),
        }
        for i, (key, srcs) in enumerate(sorted(edge_sources.items()))
        for (h, rel, t) in [key]
    ]

    write_jsonl(wd / "docs.jsonl", sorted(docs_by_id.values(), key=lambda d: d["doc_id"]))
    write_jsonl(wd / "nodes.jsonl", merged_nodes)
    write_jsonl(wd / "edges.jsonl", merged_edges)

    type_counts, relation_counts = defaultdict(int), defaultdict(int)
    for n in merged_nodes:
        type_counts[n["type"]] += 1
    for e in merged_edges:
        relation_counts[e["relation"]] += 1
    stats = {
        "dataset": args.dataset,
        "splits": splits,
        "n_nodes": len(merged_nodes),
        "n_edges": len(merged_edges),
        "n_docs": len(docs_by_id),
        "type_counts": dict(sorted(type_counts.items(), key=lambda kv: -kv[1])),
        "relation_counts": dict(sorted(relation_counts.items(), key=lambda kv: -kv[1])[:50]),
    }
    (wd / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2))

    print(f"  nodes: {len(all_nodes)} -> {len(merged_nodes)} "
          f"(merged {len(all_nodes) - len(merged_nodes)}), edges: {len(all_edges)} -> {len(merged_edges)}")

    # semantic-search index over merged nodes
    client = LLMClient(wd / "llm_cache")
    descs, entity_ids = node_descriptions(wd)
    print(f"  building merged nodes index ({len(descs)} nodes)...")
    build_index(client, descs, wd / "index/nodes", [{"entity_id": i} for i in entity_ids])
    print(f"  done. merged graph at {wd}")


if __name__ == "__main__":
    main()
