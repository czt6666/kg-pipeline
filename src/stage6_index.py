"""Stage 6: build FAISS indices for retrieval (DESIGN.md 6).

nodes.faiss   — embedding of "{name} ({type}): " + up to 3 linearized triples per node.
passages.faiss — embedding of each document's text.
Both use cosine similarity (IndexFlatIP over L2-normalized vectors). Index maps are
parallel arrays; map[i] is the entity_id / {doc_id, chunk_id} for faiss row i.
"""
import argparse
import json
from pathlib import Path

import faiss
import numpy as np

from core.common import read_jsonl, work_dir, write_jsonl
from core.llm import LLMClient
from metrics_gscore import linearize


def node_descriptions(wd: Path):
    nodes = list(read_jsonl(wd / "nodes.jsonl"))
    edges = list(read_jsonl(wd / "edges.jsonl"))
    name_by_id = {n["entity_id"]: n["name"] for n in nodes}

    triples_by_entity = {}
    for e in edges:
        head_name = name_by_id.get(e["head"])
        tail_name = name_by_id.get(e["tail"])
        if head_name and tail_name:
            triples_by_entity.setdefault(e["head"], []).append(
                {"head": head_name, "relation": e["relation"], "tail": tail_name}
            )

    descs, ids = [], []
    for n in nodes:
        triples = triples_by_entity.get(n["entity_id"], [])
        parts = [linearize(t) for t in triples[:3]]
        # also include intrinsic attributes as triples
        for rel, values in n["attributes"].items():
            for v in values[:3]:
                parts.append(f"{n['name']} {rel} {v}")
        desc = f"{n['name']} ({n['type']}): " + " ; ".join(parts) if parts else f"{n['name']} ({n['type']})"
        descs.append(desc)
        ids.append(n["entity_id"])
    return descs, ids


def build_index(client, texts: list[str], out_prefix: Path, map_rows: list):
    vecs = []
    bs = 64
    for i in range(0, len(texts), bs):
        vecs.extend(client.embed(texts[i:i + bs]))
    mat = np.array(vecs, dtype="float32")
    mat = mat / np.linalg.norm(mat, axis=1, keepdims=True)
    idx = faiss.IndexFlatIP(mat.shape[1])
    idx.add(mat)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(idx, str(out_prefix.with_suffix(".faiss")))
    write_jsonl(out_prefix.with_suffix(".index_map.json"), map_rows)
    return len(texts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="docred")
    ap.add_argument("--split", default="eval200")
    args = ap.parse_args()

    wd = work_dir(args.dataset, args.split)
    client = LLMClient(wd / "llm_cache")

    # nodes index
    descs, entity_ids = node_descriptions(wd)
    print(f"building nodes index ({len(descs)} nodes)...")
    n_nodes = build_index(client, descs, wd / "index/nodes", [{"entity_id": i} for i in entity_ids])
    print(f"  nodes index: {n_nodes} rows")

    # passages index
    docs = list(read_jsonl(wd / "docs.jsonl"))
    print(f"building passages index ({len(docs)} docs)...")
    n_docs = build_index(client, [d["text"] for d in docs], wd / "index/passages",
                         [{"doc_id": d["doc_id"], "chunk_id": None} for d in docs])
    print(f"  passages index: {n_docs} rows")


if __name__ == "__main__":
    main()
