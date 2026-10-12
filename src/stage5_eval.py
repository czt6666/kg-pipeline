"""Stage 5: build triples_eval.jsonl from nodes/edges (attributes expanded back into
triples) and compute BLEU/ROUGE/BERTScore + GenRES(TS/US/FS/GS/CS) against gold.jsonl.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from core.common import REPO_ROOT, read_jsonl, work_dir, write_jsonl
from core.llm import LLMClient
from metrics_gscore import compute_bertscore, compute_bleu_rouge
from metrics_genres import (
    _embed_all_triples,
    compute_completeness,
    compute_factualness,
    compute_granularity,
    compute_topical_similarity,
    compute_uniqueness,
)
from prompting import PromptStore


def build_triples_eval(wd: Path):
    nodes = {n["entity_id"]: n for n in read_jsonl(wd / "nodes.jsonl")}
    triples_by_doc = defaultdict(list)

    for e in read_jsonl(wd / "edges.jsonl"):
        head_name = nodes.get(e["head"], {}).get("name")
        tail_name = nodes.get(e["tail"], {}).get("name")
        if head_name is None or tail_name is None:
            continue
        triples_by_doc[e["doc_id"]].append(
            {"head_name": head_name, "relation": e["relation"], "pid": e["pid"],
             "tail_name": tail_name, "source": "edge"}
        )

    for n in nodes.values():
        for relation, values in n["attributes"].items():
            for v in values:
                triples_by_doc[n["doc_id"]].append(
                    {"head_name": n["name"], "relation": relation, "pid": None,
                     "tail_name": v, "source": "attribute"}
                )

    rows = [{"doc_id": doc_id, "triples": triples} for doc_id, triples in triples_by_doc.items()]
    write_jsonl(wd / "triples_eval.jsonl", rows)
    return {r["doc_id"]: r["triples"] for r in rows}


def to_hrt(triples_eval_row):
    return [{"head": t["head_name"], "relation": t["relation"], "tail": t["tail_name"]} for t in triples_eval_row]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="docred")
    ap.add_argument("--split", default="eval200")
    ap.add_argument("--skip-bertscore", action="store_true")
    ap.add_argument("--skip-genres", action="store_true")
    args = ap.parse_args()

    wd = work_dir(args.dataset, args.split)

    pred_by_doc_raw = build_triples_eval(wd)
    doc_ids_with_triples = set(pred_by_doc_raw.keys())

    docs = {d["doc_id"]: d for d in read_jsonl(wd / "docs.jsonl")}
    gold_raw = {g["doc_id"]: g["triples"] for g in read_jsonl(wd / "gold.jsonl")}

    # every doc_id in docs.jsonl must appear in both dicts, even if it produced 0 triples
    pred_triples_by_doc = {doc_id: to_hrt(pred_by_doc_raw.get(doc_id, [])) for doc_id in docs}
    gold_triples_by_doc = {doc_id: gold_raw.get(doc_id, []) for doc_id in docs}
    doc_texts = {doc_id: d["text"] for doc_id, d in docs.items()}

    n_pred = sum(len(v) for v in pred_triples_by_doc.values())
    n_gold = sum(len(v) for v in gold_triples_by_doc.values())
    print(f"docs: {len(docs)}, predicted triples: {n_pred}, gold triples: {n_gold}")

    # merge into any existing metrics.json (e.g. from a prior --skip-genres run) instead
    # of clobbering fields computed by a previous invocation with different --skip flags
    existing_path = wd / "eval" / "metrics.json"
    metrics = json.loads(existing_path.read_text()) if existing_path.exists() else {}
    metrics.update({
        "dataset": args.dataset,
        "split": args.split,
        "n_docs": len(docs),
        "n_pred_triples": n_pred,
        "n_gold_triples": n_gold,
    })

    print("computing BLEU/ROUGE...")
    br = compute_bleu_rouge(pred_triples_by_doc, gold_triples_by_doc)
    metrics["bleu"] = br["bleu"]
    metrics["rouge"] = br["rouge"]
    print(f"  BLEU: {br['bleu']}")
    print(f"  ROUGE: {br['rouge']}")

    if not args.skip_bertscore:
        print("computing BERTScore (downloads roberta-large on first run)...")
        bs = compute_bertscore(pred_triples_by_doc, gold_triples_by_doc)
        metrics["bertscore"] = bs
        print(f"  BERTScore: {bs}")

    if not args.skip_genres:
        client = LLMClient(wd / "llm_cache")

        print("computing TS (topical similarity)...")
        lda_dir = REPO_ROOT / "data/raw/genres_reference"
        ts = compute_topical_similarity(pred_triples_by_doc, doc_texts, lda_dir)
        print(f"  TS: {ts}")

        print("embedding all unique triples for US/CS...")
        embedding_cache = _embed_all_triples(client, pred_triples_by_doc, gold_triples_by_doc)

        print("computing US (uniqueness)...")
        us = compute_uniqueness(pred_triples_by_doc, embedding_cache)
        print(f"  US: {us}")

        print("computing CS (completeness)...")
        cs = compute_completeness(pred_triples_by_doc, gold_triples_by_doc, embedding_cache)
        print(f"  CS: {cs}")

        print("computing FS (factualness, LLM judge)...")
        prompt_asset = PromptStore().evaluation_genres()
        fact_prompt = prompt_asset.read_text("fact_checker")
        fs = compute_factualness(client, pred_triples_by_doc, doc_texts, fact_prompt)
        print(f"  FS: {fs}")

        print("computing GS (granularity, LLM judge)...")
        gran_prompt = prompt_asset.read_text("granularity_checker")
        gs = compute_granularity(client, pred_triples_by_doc, gran_prompt)
        print(f"  GS: {gs}")

        metrics["genres"] = {"ts": ts, "us": us, "fs": fs, "gs": gs, "cs": cs}

    out_path = wd / "eval" / "metrics.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
