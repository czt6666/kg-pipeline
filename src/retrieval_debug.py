"""Standalone CLI for the hybrid retrieval module -- prints each stage's intermediate
output for a single term, so lexical/semantic/graph-pattern/fusion can be debugged one at
a time without going through serve.py or the eval harness.

Usage:
    .venv/bin/python src/retrieval_debug.py --dataset TCM --merge merged_neike --term 石淋证
"""
import argparse

from core.common import graph_dir
from core.llm import LLMClient
from graph.retrieval.lexical import lexical_search
from graph.retrieval.pipeline import expand_entity, resolve_candidates
from graph.retrieval.semantic import semantic_search


def _print_hits(hits, extra_key=None):
    if not hits:
        print("  (no hits)")
        return
    for h in hits:
        extra = f" [{h[extra_key]}]" if extra_key and extra_key in h else ""
        print(f"  [{h['score']:.3f}] {h['name']} ({h['type']}){extra}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--merge", default="merged_neike", help="data/graph/{dataset}/{merge}")
    ap.add_argument("--term", required=True)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--stage", choices=["lexical", "semantic", "fusion", "full"], default="full",
                     help="stop after this stage, for isolating where a bad result comes from")
    args = ap.parse_args()

    wd = graph_dir(args.dataset, args.merge)
    client = LLMClient(wd / "llm_cache")

    print(f"=== lexical (top {args.top_k}) ===")
    lex = lexical_search(wd, args.term, top_k=args.top_k)
    _print_hits(lex, extra_key="tier")
    if args.stage == "lexical":
        return

    print(f"\n=== semantic (top {args.top_k}) ===")
    sem = semantic_search(client, args.term, wd, top_k=args.top_k)
    _print_hits(sem)
    if args.stage == "semantic":
        return

    print(f"\n=== fused candidates (top {args.top_k}) ===")
    candidates = resolve_candidates(wd, args.term, client, top_k=args.top_k)
    for c in candidates:
        ch = c["channels"]
        print(f"  [{c['fused_score']:.4f}] {c['name']} ({c['type']}) "
              f"lex={ch['lexical_rank']} sem={ch['semantic_rank']} deg={ch['degree']}")
    if args.stage == "fusion" or not candidates:
        return

    top = candidates[0]
    print(f"\n=== graph pattern + present (seed: {top['name']} / {top['entity_id']}) ===")
    expanded = expand_entity(wd, top["entity_id"], top_k=args.top_k)
    print(f"pattern hit count: {len(expanded['patterns'])}")
    print()
    print(expanded["text"])


if __name__ == "__main__":
    main()
