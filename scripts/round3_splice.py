"""把 v3_68（新 prompt 规则6重新抽取的 68 篇随证加减相关文档）拼回 neike_conn_v2，
产出 neike_conn_v3。安全阀同 round2_splice.py：新三元组数量比旧的少就保留旧结果。
"""
import json
import shutil
from pathlib import Path

BASE = Path("data/work/TCM/neike_conn_v2")
CTX = Path("data/work/TCM/neike_conn_v3_68")
OUT = Path("data/work/TCM/neike_conn_v3")
TARGET_IDS = set(json.load(open("research/round3_target_docs.json", encoding="utf-8")))


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def write_jsonl(p, rows):
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(BASE, OUT)

    old_valid = {r["doc_id"]: r for r in load_jsonl(BASE / "extraction_valid.jsonl")}
    new_valid = {r["doc_id"]: r for r in load_jsonl(CTX / "extraction_valid.jsonl")}
    new_raw = {r["doc_id"]: r for r in load_jsonl(CTX / "extraction_raw.jsonl")}

    kept_new, kept_old = [], []
    for doc_id in sorted(TARGET_IDS):
        o, n = old_valid.get(doc_id), new_valid.get(doc_id)
        if o is None or n is None:
            print(f"WARN missing {doc_id} in {'old' if o is None else 'new'}, skipping")
            continue
        if len(n["triples"]) >= len(o["triples"]):
            kept_new.append(doc_id)
        else:
            kept_old.append((doc_id, len(o["triples"]), len(n["triples"])))

    print(f"kept new extraction for {len(kept_new)} docs")
    print(f"kept OLD extraction (safety valve, new < old triple count) for {len(kept_old)} docs:")
    for doc_id, o_n, n_n in kept_old:
        print(f"    {doc_id}: old={o_n} new={n_n}")

    valid_rows = load_jsonl(BASE / "extraction_valid.jsonl")
    valid_by_id = {r["doc_id"]: r for r in valid_rows}
    for doc_id in kept_new:
        valid_by_id[doc_id] = new_valid[doc_id]
    write_jsonl(OUT / "extraction_valid.jsonl", list(valid_by_id.values()))

    raw_rows = load_jsonl(BASE / "extraction_raw.jsonl")
    raw_by_id = {r["doc_id"]: r for r in raw_rows}
    for doc_id in kept_new:
        raw_by_id[doc_id] = new_raw[doc_id]
    write_jsonl(OUT / "extraction_raw.jsonl", list(raw_by_id.values()))

    print(f"\nwrote spliced split to {OUT}")


if __name__ == "__main__":
    main()
