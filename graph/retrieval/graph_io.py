"""Shared node/edge loading for the hybrid pipeline modules (lexical.py,
graph_patterns.py). Split out on its own so neither module needs to depend on a
"basic search" module for a two-line file read."""
from __future__ import annotations

from pathlib import Path

from core.common import read_jsonl


def load_nodes_edges(wd: Path):
    """Returns (nodes: {entity_id: node_dict}, edges: [edge_dict, ...])."""
    nodes = {n["entity_id"]: n for n in read_jsonl(wd / "nodes.jsonl")}
    edges = list(read_jsonl(wd / "edges.jsonl"))
    return nodes, edges
