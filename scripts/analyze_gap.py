"""Attribution analysis for DocRED eval200 gap (BL-F1 47.6 vs 52.94, CS 35.4%).

Breaks the gold-vs-pred gap into its components:
  A. Exact-triple P/R/F1 (normalized strings) — how many gold triples we reproduce verbatim.
  B. Relation-level recall — which relations we systematically miss.
  C. Same-relation-but-different-entities — is the miss due to relation choice or entity naming?
  D. Entity-name surface mismatch — gold head/tail vs pred head/tail substring relation.
  E. Per-doc recall distribution — are a few docs driving the gap?
"""
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

WD = Path("data/work/docred/eval200")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s))
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load(path):
    return {r["doc_id"]: r["triples"] for r in (json.loads(l) for l in open(path))}


gold = load(WD / "gold.jsonl")
triples_eval = load(WD / "triples_eval.jsonl")

# pred triples from triples_eval use head_name/tail_name; convert to {head,relation,tail}
pred = {}
for doc_id, triples in triples_eval.items():
    pred[doc_id] = [
        {"head": t["head_name"], "relation": t["relation"], "tail": t["tail_name"]}
        for t in triples
    ]


def triple_key(t):
    return (norm(t["head"]), norm(t["relation"]), norm(t["tail"]))


def triple_rel_key(t):
    return norm(t["relation"])


# --- A. exact triple match ---
exact_tp = 0
for doc_id, gold_ts in gold.items():
    gold_keys = {triple_key(t) for t in gold_ts}
    pred_keys = {triple_key(t) for t in pred.get(doc_id, [])}
    exact_tp += len(gold_keys & pred_keys)

n_gold = sum(len(v) for v in gold.values())
n_pred = sum(len(v) for v in pred.values())
print("=" * 70)
print("A. EXACT TRIPLE MATCH (normalized head/relation/tail)")
print(f"  gold={n_gold}  pred={n_pred}")
print(f"  exact matched gold triples: {exact_tp}")
print(f"  exact recall  = {exact_tp/n_gold:.4f}")
exact_prec = exact_tp / n_pred
print(f"  exact precision = {exact_prec:.4f}")
print(f"  exact F1 = {2*exact_tp/(n_gold+n_pred):.4f}")

# --- B. relation-level recall ---
print("=" * 70)
print("B. RELATION-LEVEL RECALL (top 30 relations by gold frequency, worst recall)")
gold_rel = Counter()
pred_rel = Counter()
rel_match = Counter()  # relation -> # gold triples with exact triple match
for doc_id, gold_ts in gold.items():
    gk = {triple_key(t) for t in gold_ts}
    pk = {triple_key(t) for t in pred.get(doc_id, [])}
    for t in gold_ts:
        r = norm(t["relation"])
        gold_rel[r] += 1
        if triple_key(t) in pk:
            rel_match[r] += 1
    for t in pred.get(doc_id, []):
        pred_rel[norm(t["relation"])] += 1

rows = []
for r, g in gold_rel.most_common():
    rows.append((r, g, pred_rel.get(r, 0), rel_match.get(r, 0)))
rows.sort(key=lambda x: x[3] / x[1])  # worst recall first
print(f"{'relation':<45} {'gold':>5} {'pred':>5} {'match':>5} {'recall':>7}")
for r, g, p, m in rows[:30]:
    print(f"{r[:45]:<45} {g:>5} {p:>5} {m:>5} {m/g:>7.3f}")

# relation categories: recall bands
buckets = Counter()
for r, g, p, m in rows:
    rr = m / g
    if rr >= 0.9:
        buckets["recall>=0.9"] += 1
    elif rr >= 0.6:
        buckets["0.6-0.9"] += 1
    elif rr >= 0.3:
        buckets["0.3-0.6"] += 1
    else:
        buckets["<0.3"] += 1
print("  relation recall bands (of", len(rows), "relations present in gold):")
for k in ["recall>=0.9", "0.6-0.9", "0.3-0.6", "<0.3"]:
    print(f"    {k}: {buckets.get(k,0)}")

# --- C. same-relation different-entity ---
print("=" * 70)
print("C. SAME-RELATION-DIFFERENT-ENTITY (miss breakdown)")
# For each gold triple, is there a pred triple with SAME relation but different entities?
same_rel_any = 0
same_rel_exact = 0
for doc_id, gold_ts in gold.items():
    pred_by_rel = defaultdict(list)
    for t in pred.get(doc_id, []):
        pred_by_rel[norm(t["relation"])].append(t)
    for t in gold_ts:
        r = norm(t["relation"])
        if r in pred_by_rel:
            same_rel_any += 1
            if any(triple_key(t) == triple_key(p) for p in pred_by_rel[r]):
                same_rel_exact += 1
print(f"  gold triples whose relation is present in pred (any entity): {same_rel_any}/{n_gold} = {same_rel_any/n_gold:.4f}")
print(f"  gold triples exactly reproduced: {same_rel_exact}/{n_gold} = {same_rel_exact/n_gold:.4f}")
# inverse-relation coverage: is the "opposite" relation present?
print("  => relation coverage is the ceiling: even with perfect entity naming, recall cap ~",
      f"{same_rel_any/n_gold:.4f}")

# --- D. entity surface mismatch ---
print("=" * 70)
print("D. ENTITY SURFACE MISMATCH (for gold triples whose relation IS in pred)")
surf_exact_head = surf_exact_tail = 0
surf_substr_head = surf_substr_tail = 0
denom = 0
for doc_id, gold_ts in gold.items():
    pred_by_rel = defaultdict(list)
    pred_head_names = {norm(t["head"]) for t in pred.get(doc_id, [])}
    pred_tail_names = {norm(t["tail"]) for t in pred.get(doc_id, [])}
    for t in gold_ts:
        if norm(t["relation"]) not in pred_by_rel:
            continue
        denom += 1
        gh, gt = norm(t["head"]), norm(t["tail"])
        if gh in pred_head_names:
            surf_exact_head += 1
        elif any(gh in p or p in gh for p in pred_head_names):
            surf_substr_head += 1
        if gt in pred_tail_names:
            surf_exact_tail += 1
        elif any(gt in p or p in gt for p in pred_tail_names):
            surf_substr_tail += 1
print(f"  (only gold triples whose relation exists in pred: {denom})")
print(f"  head exact surface in pred: {surf_exact_head}/{denom} = {surf_exact_head/max(denom,1):.4f}")
print(f"  head substring/superstring: {surf_substr_head}/{denom} = {surf_substr_head/max(denom,1):.4f}")
print(f"  tail exact surface in pred: {surf_exact_tail}/{denom} = {surf_exact_tail/max(denom,1):.4f}")
print(f"  tail substring/superstring: {surf_substr_tail}/{denom} = {surf_substr_tail/max(denom,1):.4f}")

# --- E. per-doc recall distribution ---
print("=" * 70)
print("E. PER-DOC EXACT RECALL DISTRIBUTION")
doc_recalls = []
for doc_id, gold_ts in gold.items():
    gk = {triple_key(t) for t in gold_ts}
    pk = {triple_key(t) for t in pred.get(doc_id, [])}
    r = len(gk & pk) / max(len(gk), 1)
    doc_recalls.append((r, doc_id, len(gk), len(pk)))
doc_recalls.sort()
print(f"  median recall: {sorted(r for r,_,_,_ in doc_recalls)[len(doc_recalls)//2]:.3f}")
print(f"  mean recall: {sum(r for r,_,_,_ in doc_recalls)/len(doc_recalls):.3f}")
print("  worst 15 docs (recall, doc_id, #gold, #pred):")
for r, doc_id, ng, np_ in doc_recalls[:15]:
    print(f"    {r:.3f}  {doc_id}  gold={ng} pred={np_}")
print("  best 5 docs:")
for r, doc_id, ng, np_ in doc_recalls[-5:]:
    print(f"    {r:.3f}  {doc_id}  gold={ng} pred={np_}")
