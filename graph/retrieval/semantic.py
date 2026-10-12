"""Semantic search for the hybrid pipeline: cosine top-K over the merged graph's node
embedding index (nodes.faiss, built by stage6_index.py / stage7_merge.py).

Self-contained (no dependency on a "basic search" module): merged graphs only ever have
nodes.faiss built, and the hybrid pipeline's input is a precise entity term, not a
question needing passage-level context, so this only ever queries the node index.
"""
from __future__ import annotations

from pathlib import Path

import faiss
import numpy as np

from core.common import read_jsonl
from .graph_io import load_nodes_edges


def semantic_search(client, term: str, wd: Path, top_k: int = 10):
    """Returns [{entity_id, name, type, score, doc_id?}, ...], sorted by score descending
    (faiss cosine similarity via inner product on L2-normalized vectors). Empty list if
    this split/merge has no node index built yet."""
    idx_path = wd / "index" / "nodes.faiss"
    map_path = wd / "index" / "nodes.index_map.json"
    if not idx_path.exists():
        return []

    qvec = np.array(client.embed([term])[0], dtype="float32")
    qvec = qvec / np.linalg.norm(qvec)

    index = faiss.read_index(str(idx_path))
    maps = list(read_jsonl(map_path))
    nodes, _ = load_nodes_edges(wd)

    scores, ids = index.search(qvec.reshape(1, -1), min(top_k, index.ntotal))
    out = []
    for score, i in zip(scores[0], ids[0]):
        if i == -1:
            continue
        entity_id = maps[i]["entity_id"]
        n = nodes.get(entity_id)
        if not n:
            continue
        entry = {"entity_id": entity_id, "name": n["name"], "type": n["type"], "score": float(score)}
        if "doc_id" in n:
            entry["doc_id"] = n["doc_id"]
        out.append(entry)
    return out
