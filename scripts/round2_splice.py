"""把 ctx40（标题路径+证型清单注入后重新抽取的 40 篇）拼回 neike_conn_v1，产出 neike_conn_v2。

安全阀（参考旧项目 retry_truncated_docs.py 的做法）：新结果三元组数量比旧的少，说明这次
撞到了模型 8192 token 硬上限被截断（清单让模型想写得更全，个别本来就很大的 chunk 反而
被顶到上限），这种情况自动放弃新结果、保留旧结果，不能让"想变好"的改动实际把内容改差。
"""
import json
import shutil
from pathlib import Path

BASE = Path("data/work/TCM/neike_conn_v1")
CTX = Path("data/work/TCM/neike_conn_v2_ctx40")
OUT = Path("data/work/TCM/neike_conn_v2")
TARGET_IDS = set(json.load(open("research/round2_target_docs_multipattern.json", encoding="utf-8")))


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
    old_raw = {r["doc_id"]: r for r in load_jsonl(BASE / "extraction_raw.jsonl")}
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

    # splice extraction_valid.jsonl
    valid_rows = load_jsonl(BASE / "extraction_valid.jsonl")
    valid_by_id = {r["doc_id"]: r for r in valid_rows}
    for doc_id in kept_new:
        valid_by_id[doc_id] = new_valid[doc_id]
    write_jsonl(OUT / "extraction_valid.jsonl", list(valid_by_id.values()))

    # splice extraction_raw.jsonl (keep parse_status/cache_key consistent with what's kept)
    raw_rows = load_jsonl(BASE / "extraction_raw.jsonl")
    raw_by_id = {r["doc_id"]: r for r in raw_rows}
    for doc_id in kept_new:
        raw_by_id[doc_id] = new_raw[doc_id]
    write_jsonl(OUT / "extraction_raw.jsonl", list(raw_by_id.values()))

    # docs.jsonl: use the context-injected text for kept_new docs so future re-runs of
    # this split stay consistent with what was actually sent to the model
    ctx_docs = {d["doc_id"]: d for d in load_jsonl(CTX / "docs.jsonl")}
    docs_rows = load_jsonl(BASE / "docs.jsonl")
    docs_by_id = {d["doc_id"]: d for d in docs_rows}
    for doc_id in kept_new:
        docs_by_id[doc_id] = ctx_docs[doc_id]
    write_jsonl(OUT / "docs.jsonl", list(docs_by_id.values()))

    print(f"\nwrote spliced split to {OUT}")


if __name__ == "__main__":
    main()
