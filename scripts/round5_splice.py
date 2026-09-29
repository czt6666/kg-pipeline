"""Round 5：Round 2 的 40 篇"多证型堆叠"文档，抽取时用的还是 Round 3 修 prompt 规则6
之前的旧版本（当时功效边规则还没补上）。现在 prompt 已经永久改了，用同一份 context
注入文本（标题路径+证型清单）+ 新 prompt 重新抽一遍，看看两个修复叠加能不能再抢救
一部分（安全阀同前）。
"""
import json
import shutil
from pathlib import Path

BASE = Path("data/work/TCM/neike_conn_v3")
CTX = Path("data/work/TCM/neike_conn_v5_retry40")
OUT = Path("data/work/TCM/neike_conn_v5")
TARGET_IDS = set(json.load(open("research/round5_retry40_docids.json", encoding="utf-8")))


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
            print(f"WARN missing {doc_id}")
            continue
        if len(n["triples"]) >= len(o["triples"]):
            kept_new.append(doc_id)
        else:
            kept_old.append((doc_id, len(o["triples"]), len(n["triples"])))

    print(f"kept new extraction for {len(kept_new)} docs")
    print(f"kept OLD (safety valve) for {len(kept_old)} docs:")
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
