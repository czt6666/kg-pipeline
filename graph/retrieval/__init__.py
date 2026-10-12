"""Retrieval package: the hybrid pipeline for agent-facing entity lookups (precise TCM
term in, ranked facts + a subgraph + readable text out).

lexical.py / semantic.py / graph_patterns.py / fusion.py / present.py are the individual
stages, wired together by pipeline.py's `hybrid_search`/`expand_entity`. See
docs/retrieval_graph_patterns.md for the graph-pattern design and src/retrieval_debug.py
for a standalone CLI to exercise it stage by stage.
"""
