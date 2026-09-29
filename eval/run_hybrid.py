"""Hybrid retrieval eval: for each case in eval/retrieval_terms.jsonl, run
retrieval.pipeline.hybrid_search(term) and check whether any expected answer shows up in
the resulting facts text. Mirrors eval/run_baseline.py's structure/match rule (see that
file's docstring) but against the new module's own contract (precise term in, facts out)
rather than eval/questions.jsonl's descriptive-sentence contract.

This is a tuning baseline, not a replacement for run_baseline.py's QA benchmark -- default
fusion weights are not expected to be optimal; --w-lexical/--w-semantic/--w-graph exist so
weights can be swept once there's a reason to prefer one setting over another.

Usage: .venv/bin/python eval/run_hybrid.py [--dataset TCM --merge merged_neike
    --cases eval/retrieval_terms.jsonl --top-k 10 --tag default]
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from retrieval.pipeline import hybrid_search  # noqa: E402


def normalize(s):
    s = re.sub(r"[（）()、，,。\s]", "", s)
    return s.rstrip("证")


def is_hit(expected, sentences):
    exp_n = [normalize(e) for e in expected if e]
    sent_n = [normalize(s) for s in sentences if s]
    return any(e and s and e in s for e in exp_n for s in sent_n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--merge", default="merged_neike")
    ap.add_argument("--cases", default=str(ROOT / "eval/retrieval_terms.jsonl"))
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--tag", default="default", help="output file suffix: eval/hybrid_results_<tag>.jsonl")
    ap.add_argument("--w-lexical", type=float, default=1.0)
    ap.add_argument("--w-semantic", type=float, default=1.0)
    ap.add_argument("--w-graph", type=float, default=0.5)
    args = ap.parse_args()

    cases = [json.loads(l) for l in open(args.cases, encoding="utf-8")]
    weights = dict(w_lexical=args.w_lexical, w_semantic=args.w_semantic, w_graph=args.w_graph)

    results = []
    hits_by_relation, total_by_relation = defaultdict(int), defaultdict(int)
    for c in cases:
        result = hybrid_search(args.dataset, args.merge, c["term"], top_k=args.top_k, **weights)
        resolved = result["resolved"]
        sentences = [f["sentence"] for f in resolved["facts"]] if resolved else []
        hit = is_hit(c["expected"], sentences)

        results.append({
            "id": c["id"], "relation": c["relation"], "term": c["term"], "expected": c["expected"],
            "resolved_name": resolved["seed"]["name"] if resolved else None,
            "resolved_type": resolved["seed"]["type"] if resolved else None,
            "hit": hit, "n_candidates": len(result["candidates"]),
        })
        total_by_relation[c["relation"]] += 1
        if hit:
            hits_by_relation[c["relation"]] += 1

    out_path = ROOT / f"eval/hybrid_results_{args.tag}.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    total_hits = sum(hits_by_relation.values())
    total = len(cases)
    print(f"overall hit rate: {total_hits}/{total} = {total_hits / total:.1%}  (weights: {weights})")
    for rel in sorted(total_by_relation):
        h, n = hits_by_relation.get(rel, 0), total_by_relation[rel]
        print(f"  {rel}: {h}/{n} = {h / n:.1%}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
