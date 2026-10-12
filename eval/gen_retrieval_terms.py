"""Generates eval/retrieval_terms.jsonl by sampling real (term, relation, expected) cases
directly from a merged graph's edges. Unlike eval/questions.jsonl (whole descriptive
sentences, built for a "user asks a question" contract), this matches the hybrid retrieval
module's actual input contract -- a precise term in, and the resulting facts should include
the expected relation target -- so it's a smoke-test/regression baseline for the module
itself (graph/retrieval/pipeline.py), not a substitute for the existing QA benchmark.

Usage: .venv/bin/python eval/gen_retrieval_terms.py [--dataset TCM --merge merged_neike
    --per-relation 10 --min-name-len 2 --seed 0]
"""
import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from core.common import graph_dir, read_jsonl

# Restrict sampling to the seed types the hybrid module actually curates named patterns for
# (see docs/retrieval_graph_patterns.md 2.2) so every generated case is answerable by the
# module as designed -- not just reachable by chance via the always-on profile pattern on
# an uncurated intermediate type (病因/治法功效/性味/脏腑经络).
CURATED_SEED_TYPES = {"疾病", "证候", "症状", "中药", "方剂"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--merge", default="merged_neike")
    ap.add_argument("--per-relation", type=int, default=10)
    ap.add_argument("--min-name-len", type=int, default=2, help="skip junk short-name head nodes")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "eval/retrieval_terms.jsonl"))
    args = ap.parse_args()

    wd = graph_dir(args.dataset, args.merge)
    nodes = {n["entity_id"]: n for n in read_jsonl(wd / "nodes.jsonl")}
    edges = list(read_jsonl(wd / "edges.jsonl"))

    # Group by (head_id, relation) -> tail names, so a term with several correct answers
    # for the same relation (e.g. 感冒 分型 many 证候) becomes one multi-answer case
    # instead of several near-duplicate single-answer ones.
    grouped = defaultdict(set)
    for e in edges:
        head, tail = nodes.get(e["head"]), nodes.get(e["tail"])
        if not head or not tail or head["type"] not in CURATED_SEED_TYPES:
            continue
        if len(head["name"]) < args.min_name_len:
            continue
        grouped[(e["head"], e["relation"])].add(tail["name"])

    by_relation = defaultdict(list)
    for (head_id, relation), tails in grouped.items():
        by_relation[relation].append((head_id, tails))

    rng = random.Random(args.seed)
    cases = []
    for relation, items in sorted(by_relation.items()):
        rng.shuffle(items)
        for head_id, tails in items[: args.per_relation]:
            head = nodes[head_id]
            cases.append({
                "id": f"rt{len(cases) + 1:03d}",
                "seed_type": head["type"],
                "relation": relation,
                "term": head["name"],
                "expected": sorted(tails),
            })

    with open(args.out, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"wrote {len(cases)} cases to {args.out}")
    print(f"relations available: {{{', '.join(f'{r}: {len(v)}' for r, v in sorted(by_relation.items()))}}}")


if __name__ == "__main__":
    main()
