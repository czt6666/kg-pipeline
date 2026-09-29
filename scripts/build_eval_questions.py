"""Builds eval/questions.jsonl: 100 grounded questions over data/work/TCM/neike source text
(CLAUDE.md step 1 — built before touching the graph). Covers 5 categories: 症状→证型,
证型→治法, 证型→主方, 方→主治证型, 病→证型列表.

Reads research/neike_patterns.jsonl (证治分类 blocks parsed straight from docs_gelun.jsonl,
grounded with the corrected disease label from research/neike_disease_boundary_map.json — see
research/round0_segmentation_bug.md for why the raw 所属疾病 field can't be trusted directly).
Every question records its source doc_id/page/verbatim quote so answers can be checked against
the original text without re-deriving anything.

Usage: .venv/bin/python scripts/build_eval_questions.py
"""
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SPLIT_RE = re.compile(r"[、，,]")


def split_symptoms(raw):
    parts = [p.strip() for p in SPLIT_RE.split(raw) if p.strip()]
    # drop trailing period-glued fragments / empty
    return [p.rstrip("。") for p in parts if p.rstrip("。")]


def clean_formula(raw):
    """代表方 field often reads '三拗汤合止嗽散加减。两方均能……' — strip the trailing
    commentary sentence and '加减/化裁' suffix noise, matching the schema's 方剂 name rule."""
    first_sentence = raw.split("。")[0]
    first_sentence = re.sub(r"(加减|化裁)$", "", first_sentence).strip()
    return first_sentence


def main():
    random.seed(42)
    records = [json.loads(l) for l in open(ROOT / "research/neike_patterns.jsonl")]
    records = [r for r in records if r["principle"] and r["formula"]]

    by_disease = {}
    for r in records:
        by_disease.setdefault(r["disease"], []).append(r)

    # Diseases known-contaminated by the round0 segmentation bug (see
    # research/round0_segmentation_bug.md) — oversample these since they're the ones we most
    # need a stable, source-grounded yardstick for once that bug is fixed.
    contaminated = {"咳嗽", "哮病", "胸痹", "头痛", "眩晕", "中风", "胃痞", "黄疸", "淋证", "血证", "痉证", "痿证"}

    diseases_sorted = sorted(by_disease.keys())
    # stratified sample: walk diseases in round-robin so questions spread across the book,
    # not clustered in whichever disease happens to have the most 证型.
    def diverse_records(n, seen_keys, key_fn):
        """Round-robin over diseases, skipping records whose key_fn() was already used."""
        out = []
        pools = {d: list(recs) for d, recs in by_disease.items()}
        for pool in pools.values():
            random.shuffle(pool)
        order = diseases_sorted[:]
        random.shuffle(order)
        # bias contaminated diseases earlier so they're not crowded out
        order.sort(key=lambda d: 0 if d in contaminated else 1)
        i = 0
        while len(out) < n and any(pools.values()):
            d = order[i % len(order)]
            i += 1
            pool = pools.get(d)
            if not pool:
                continue
            r = pool.pop()
            k = key_fn(r)
            if k in seen_keys:
                continue
            seen_keys.add(k)
            out.append(r)
        return out

    questions = []
    qid = 0

    def add(qtype, question, answer, evidence, note=None):
        nonlocal qid
        qid += 1
        q = {
            "id": f"q{qid:03d}",
            "type": qtype,
            "question": question,
            "answer": answer,
            "evidence": evidence,
        }
        if note:
            q["note"] = note
        questions.append(q)

    # A. 症状→证型 (20)
    seen = set()
    for r in diverse_records(20, seen, lambda r: (r["disease"], r["pattern"])):
        syms = split_symptoms(r["symptoms_raw"])
        if len(syms) < 3:
            continue
        pick = syms[: min(5, max(3, len(syms) // 2))]
        add(
            "症状→证型",
            f"患者属于{r['disease']}，出现以下症状：{'、'.join(pick)}，属于什么证型？",
            r["pattern"],
            {"doc_id": r["doc_id"], "page": r["page_start"], "quote": r["symptoms_raw"]},
        )

    # B. 证型→治法 (20)
    seen = set()
    for r in diverse_records(20, seen, lambda r: (r["disease"], r["pattern"])):
        add(
            "证型→治法",
            f"{r['disease']}的{r['pattern']}，治法是什么？",
            r["principle"],
            {"doc_id": r["doc_id"], "page": r["page_start"], "quote": f"治法：{r['principle']}"},
        )

    # C. 证型→主方 (20)
    seen = set()
    for r in diverse_records(20, seen, lambda r: (r["disease"], r["pattern"])):
        add(
            "证型→主方",
            f"{r['disease']}的{r['pattern']}，代表方是什么？",
            clean_formula(r["formula"]),
            {"doc_id": r["doc_id"], "page": r["page_start"], "quote": f"代表方：{r['formula']}"},
            note=f"原文全文：{r['formula']}",
        )

    # D. 方→主治证型 (20) — scoped to a disease to avoid cross-disease ambiguity (a formula
    # name can recur under different diseases with unrelated indications).
    seen = set()
    formula_use_within_disease = {}
    for r in records:
        formula_use_within_disease.setdefault((r["disease"], clean_formula(r["formula"])), []).append(r)
    candidates = [
        r for r in records
        if len(formula_use_within_disease[(r["disease"], clean_formula(r["formula"]))]) == 1
    ]
    by_disease_d = {}
    for r in candidates:
        by_disease_d.setdefault(r["disease"], []).append(r)
    pools_d = {d: list(v) for d, v in by_disease_d.items()}
    for pool in pools_d.values():
        random.shuffle(pool)
    order_d = list(pools_d.keys())
    random.shuffle(order_d)
    order_d.sort(key=lambda d: 0 if d in contaminated else 1)
    i = 0
    picked_d = []
    seen_pat = set()
    while len(picked_d) < 20 and any(pools_d.values()):
        d = order_d[i % len(order_d)]
        i += 1
        pool = pools_d.get(d)
        if not pool:
            continue
        r = pool.pop()
        if (r["disease"], r["pattern"]) in seen_pat:
            continue
        seen_pat.add((r["disease"], r["pattern"]))
        picked_d.append(r)
    for r in picked_d:
        fname = clean_formula(r["formula"])
        add(
            "方→主治证型",
            f"在{r['disease']}的辨证分型中，以{fname}为代表方的是什么证型？",
            r["pattern"],
            {"doc_id": r["doc_id"], "page": r["page_start"], "quote": f"代表方：{r['formula']}"},
        )

    # E. 病→证型列表 (20)
    disease_list = sorted(by_disease.keys())
    random.shuffle(disease_list)
    disease_list.sort(key=lambda d: 0 if d in contaminated else 1)
    picked_e = disease_list[:20]
    for d in picked_e:
        recs = by_disease[d]
        patterns = sorted(set(r["pattern"] for r in recs))
        doc_ids = sorted(set(r["doc_id"] for r in recs))
        pages = sorted(set(r["page_start"] for r in recs))
        add(
            "病→证型列表",
            f"{d}辨证论治分为哪些证型？",
            patterns,
            {"doc_id": doc_ids, "page": pages},
        )

    out_path = ROOT / "eval/questions.jsonl"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    by_type = {}
    for q in questions:
        by_type[q["type"]] = by_type.get(q["type"], 0) + 1
    print(f"wrote {len(questions)} questions -> {out_path}")
    for t, c in by_type.items():
        print(f"  {t}: {c}")


if __name__ == "__main__":
    main()
