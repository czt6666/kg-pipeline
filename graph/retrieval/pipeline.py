"""Top-level orchestration for the hybrid retrieval module: lexical + semantic + graph
pattern -> fusion -> readable text. This is what the graph API's `/api/kg/retrieval/search` and
`eval/run_hybrid.py` call; `src/retrieval_debug.py` exercises the earlier stages directly
for finer-grained debugging.

Three entry points, split by cost:
  - `resolve_candidates`: cheap (two search calls + RRF over a small candidate set).
  - `expand_entity`: graph pattern search + text rendering, still LLM-free -- fast enough
    to run inline with every search/disambiguation click.
  - `generate_summary`: the one LLM round-trip (a few seconds). Deliberately a separate
    call rather than folded into `expand_entity`, so the UI can render facts/subgraph the
    instant `expand_entity` returns and fetch the prose summary asynchronously afterward
    instead of blocking the whole panel on the LLM (see services/backend_server.py + services/kg_server.py routes and Retrieval.jsx's fetchSummary). Re-running graph_pattern_search
    here is intentional, not an inefficiency worth caching around -- it's local jsonl
    reads + an adjacency walk, cheap next to the LLM call it precedes.
"""
from __future__ import annotations

from pathlib import Path

from core.common import graph_dir, read_jsonl
from core.llm import LLMClient
from .fusion import fuse_candidates, node_degree, rank_facts
from .graph_patterns import graph_pattern_search
from .lexical import lexical_search
from .present import present_result
from .semantic import semantic_search
from .summarize import SUMMARY_MODEL, summarize_facts

CANDIDATE_POOL = 20  # per-channel top_k before fusion narrows to the caller's top_k


def resolve_candidates(wd: Path, term: str, client: LLMClient, top_k: int = 10, **weights):
    """Runs lexical + semantic + graph-degree fusion. Returns the fused candidate list
    (see fusion.fuse_candidates for the per-entry shape)."""
    lex = lexical_search(wd, term, top_k=CANDIDATE_POOL)
    sem = semantic_search(client, term, wd, top_k=CANDIDATE_POOL)
    degree = node_degree(wd)
    return fuse_candidates(lex, sem, degree, top_k=top_k, **weights)


def _build_subgraph(seed: dict, profile: dict, ranked_patterns: list[dict], nodes: dict):
    """Flattens the profile fan-out + every ranked pattern's hops into a plain
    {nodes, edges} graph GraphCanvas can render directly -- the same shape used
    everywhere else in the app (entity_id/name/type nodes; head/relation/tail/condition
    edges). This is what makes the retrieval panel show "the subgraph that produced this
    explanation", not just a text list of facts with no visual structure behind them."""
    node_ids = {seed["entity_id"]}
    edges, seen = [], set()

    def add_edge(head, relation, tail, condition):
        cond_key = condition if isinstance(condition, str) else None
        key = (head, relation, tail, cond_key)
        if key in seen:
            return
        seen.add(key)
        node_ids.add(head)
        node_ids.add(tail)
        edges.append({"head": head, "relation": relation, "tail": tail, "condition": condition})

    for relation, targets in (profile.get("out") or {}).items():
        for t in targets:
            add_edge(seed["entity_id"], relation, t["entity_id"], t.get("condition"))
    for relation, sources in (profile.get("in") or {}).items():
        for h in sources:
            add_edge(h["entity_id"], relation, seed["entity_id"], h.get("condition"))
    for p in ranked_patterns:
        for hop in p["hops"]:
            add_edge(hop["head"], hop["relation"], hop["tail"], hop.get("condition"))

    subgraph_nodes = []
    for eid in node_ids:
        n = nodes.get(eid)
        if n:
            subgraph_nodes.append({"entity_id": eid, "name": n["name"], "type": n["type"]})
        elif eid == seed["entity_id"]:
            subgraph_nodes.append({"entity_id": eid, "name": seed["name"], "type": seed["type"]})
    return {"nodes": subgraph_nodes, "edges": edges}


def _resolve_and_present(wd: Path, entity_id: str, top_k: int):
    """The LLM-free half of "explain this entity" -- graph_pattern_search + rank_facts +
    present_result -- shared by expand_entity (which also needs the subgraph) and
    generate_summary (which only needs presented['facts']). Returns
    (seed, profile, ranked_patterns, presented, nodes), or None if entity_id is unknown."""
    nodes = {n["entity_id"]: n for n in read_jsonl(wd / "nodes.jsonl")}
    seed_node = nodes.get(entity_id)
    if seed_node is None:
        return None
    seed = {"entity_id": entity_id, "name": seed_node["name"], "type": seed_node["type"]}
    result = graph_pattern_search(wd, entity_id)
    ranked_patterns = rank_facts(result["patterns"], top_k=top_k)
    presented = present_result(seed, result["profile"], ranked_patterns, nodes, top_k=top_k)
    return seed, result["profile"], ranked_patterns, presented, nodes


def expand_entity(wd: Path, entity_id: str, top_k: int = 10):
    """Graph-pattern search + fact ranking + text rendering for one already-resolved
    entity. Returns {"seed", "profile", "patterns", "subgraph", "text", "facts",
    "summary": None} (see present.present_result for text/facts, _build_subgraph for
    subgraph). `summary` is always None here -- deliberately LLM-free, see module
    docstring and generate_summary(); callers display the template-rendered `text` until
    the async summary call resolves."""
    resolved = _resolve_and_present(wd, entity_id, top_k)
    if resolved is None:
        return None
    seed, profile, ranked_patterns, presented, nodes = resolved
    subgraph = _build_subgraph(seed, profile, ranked_patterns, nodes)
    return {"seed": seed, "profile": profile, "patterns": ranked_patterns,
            "subgraph": subgraph, "summary": None, **presented}


def generate_summary(wd: Path, entity_id: str, top_k: int = 10) -> str | None:
    """The one LLM call in this module: an async-fetched paragraph rewrite of the same
    facts expand_entity(wd, entity_id, top_k) would present. Returns the summary text, or
    None if entity_id is unknown or the call fails (summarize.summarize_facts already
    swallows LLMError; callers should fall back to expand_entity's `text` field)."""
    resolved = _resolve_and_present(wd, entity_id, top_k)
    if resolved is None:
        return None
    seed, _profile, _ranked_patterns, presented, _nodes = resolved
    client = LLMClient(wd / "llm_cache", model=SUMMARY_MODEL)
    return summarize_facts(client, seed, presented["facts"])


def hybrid_search(dataset: str, merge: str, term: str, top_k: int = 10, expand: bool = True,
                  **weights):
    """Full pipeline for one term. Returns:
    {"term", "candidates": [...], "resolved": {...} | None} where `resolved` is
    `expand_entity`'s output for the top-ranked candidate (summary always None -- fetch it
    separately via generate_summary/`/api/kg/retrieval/summary`), or None if nothing matched
    at all (candidates is then also empty) -- callers should treat that as "no results",
    not an error.

    `expand=False` skips graph-pattern search entirely and returns `resolved: None` even
    when candidates exist -- for callers (e.g. a plain "find this entity to jump to it"
    search box) that only need the candidate list, not a full explanation.
    """
    wd = graph_dir(dataset, merge)
    client = LLMClient(wd / "llm_cache")
    candidates = resolve_candidates(wd, term, client, top_k=top_k, **weights)

    resolved = None
    if expand and candidates:
        resolved = expand_entity(wd, candidates[0]["entity_id"], top_k=top_k)
    return {"term": term, "candidates": candidates, "resolved": resolved}
