"""Retrieval: dual-path graph search + semantic retrieval (DESIGN.md 8).

Graph search   — BFS from seed nodes along schema relations, constrained by node types
                 and hop budget (config.bfs_hops / bfs_node_budget).
Semantic search — cosine top-K over nodes.faiss and passages.faiss, plus a lexical
                 edit-distance path over node name/aliases. The two paths are returned
                 side-by-side (DESIGN.md 8.2), not merged.
"""
import argparse
import json
import re
from collections import deque
from pathlib import Path

import faiss
import numpy as np

from common import load_config, read_jsonl, work_dir
from llm_client import LLMClient


def _load_nodes_edges(wd: Path):
    nodes = {n["entity_id"]: n for n in read_jsonl(wd / "nodes.jsonl")}
    edges = list(read_jsonl(wd / "edges.jsonl"))
    adj = {}
    for e in edges:
        adj.setdefault(e["head"], []).append((e["tail"], e["relation"]))
    return nodes, edges, adj


def semantic_search(client, query, wd: Path, top_k: int = 10):
    """Returns {"nodes": [...], "passages": [...]}."""
    qvec = np.array(client.embed([query])[0], dtype="float32")
    qvec = qvec / np.linalg.norm(qvec)

    out = {"nodes": [], "passages": []}
    for kind in ("nodes", "passages"):
        idx_path = wd / "index" / f"{kind}.faiss"
        map_path = wd / "index" / f"{kind}.index_map.json"
        if not idx_path.exists():
            continue
        index = faiss.read_index(str(idx_path))
        maps = list(read_jsonl(map_path))
        scores, ids = index.search(qvec.reshape(1, -1), min(top_k, index.ntotal))
        for score, i in zip(scores[0], ids[0]):
            if i == -1:
                continue
            entry = {"score": float(score), **maps[i]}
            if kind == "nodes":
                n = _load_nodes_edges(wd)[0].get(maps[i]["entity_id"])
                if n:
                    entry["name"] = n["name"]
                    entry["type"] = n["type"]
                    # Per-split nodes have a single doc_id; merged (cross-doc) nodes have
                    # source_doc_ids instead — only surface doc_id when it's unambiguous.
                    if "doc_id" in n:
                        entry["doc_id"] = n["doc_id"]
            else:
                docs = {d["doc_id"]: d for d in read_jsonl(wd / "docs.jsonl")}
                entry["text"] = docs.get(maps[i]["doc_id"], {}).get("text", "")
            out[kind].append(entry)
    return out


def graph_search(wd: Path, seed_ids: list[str], relations: set[str] | None = None,
                 types: set[str] | None = None, hops: int = 2, node_budget: int = 500):
    """BFS from seed nodes along schema edges. Returns {nodes, edges} subgraph."""
    nodes, edges, adj = _load_nodes_edges(wd)
    visited = set(seed_ids)
    frontier = deque(seed_ids)
    sub_edges = []
    for _ in range(hops):
        nxt = []
        for u in frontier:
            for v, rel in adj.get(u, []):
                if relations and rel not in relations:
                    continue
                if types and nodes.get(v, {}).get("type") not in types:
                    continue
                sub_edges.append({"head": u, "relation": rel, "tail": v})
                if v not in visited:
                    visited.add(v)
                    nxt.append(v)
                    if len(visited) >= node_budget:
                        break
            if len(visited) >= node_budget:
                break
        frontier = nxt
        if not frontier:
            break
    sub_nodes = [{"entity_id": i, **nodes[i]} for i in visited if i in nodes]
    return {"nodes": sub_nodes, "edges": sub_edges}


def lexical_search(wd: Path, query: str, top_k: int = 10):
    """Edit-distance match over node name/aliases (normalized)."""
    import difflib
    nodes, _, _ = _load_nodes_edges(wd)
    q = query.lower()
    scored = []
    for n in nodes.values():
        surfaces = [n["name"]] + list(n.get("aliases", []))
        best = max((difflib.SequenceMatcher(None, q, s.lower()).ratio() for s in surfaces), default=0.0)
        scored.append((best, n))
    scored.sort(key=lambda x: -x[0])
    return [{"entity_id": n["entity_id"], "name": n["name"], "type": n["type"], "score": s,
              **({"doc_id": n["doc_id"]} if "doc_id" in n else {})}
            for s, n in scored[:top_k] if s > 0.0]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="docred")
    ap.add_argument("--split", default="eval200")
    ap.add_argument("--query", required=True)
    args = ap.parse_args()
    wd = work_dir(args.dataset, args.split)
    client = LLMClient(wd / "llm_cache")
    sem = semantic_search(client, args.query, wd, top_k=5)
    print("=== semantic nodes ===")
    for n in sem["nodes"]:
        print(f"  [{n['score']:.3f}] {n.get('name')} ({n.get('type')})")
    print("=== semantic passages ===")
    for p in sem["passages"]:
        print(f"  [{p['score']:.3f}] {p['text'][:80]}")
    print("=== lexical ===")
    for n in lexical_search(wd, args.query, top_k=5):
        print(f"  [{n['score']:.3f}] {n['name']} ({n['type']})")
