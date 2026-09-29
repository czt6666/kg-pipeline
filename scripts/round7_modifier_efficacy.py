"""Round 7：规则式（不调模型）补"随证加减"里药物→功效的边。

背景：Round 3 靠改 prompt 规则 6 让模型自己去补这类边，65/68 篇命中，但 Round 6 排查
发现命中不了的文档（如 0027）即使换了新 prompt 依然漏建——模型在这类"若…加A、B、C+
功效短语"的从句里，多数情况下遵守了新规则，但不是 100%。规则本身很机械（"加"后面跟
一串已经被模型正确识别成"中药"类型的实体，紧接着是一个已经被模型正确识别成"治法功效"
类型的实体，两者之间没有句号/分号分隔），没必要每次都赌模型会不会遵守——直接用正则
在原文里找这个模式，对着已经抽取出来的实体表（不调用模型，不会引入新实体/新幻觉）
建"功效"边，天然带原文位置作为依据。

只处理"孤立的治法功效实体"：如果它已经有边了（说明是正常的"治法"而不是加减药物的
功效描述），不碰，避免破坏已有的正确内容。
"""
import argparse
import json
import re
from pathlib import Path


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def write_jsonl(p, rows):
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--doc-ids", required=True)
    args = ap.parse_args()

    wd = Path("data/work/TCM") / args.split
    target_ids = set(json.load(open(args.doc_ids, encoding="utf-8")))

    docs = {d["doc_id"]: d for d in load_jsonl(wd / "docs.jsonl")}
    valid = load_jsonl(wd / "extraction_valid.jsonl")
    valid_by_id = {r["doc_id"]: r for r in valid}

    n_edges_added = 0
    n_docs_touched = 0
    evidence_log = []

    for doc_id in sorted(target_ids):
        rec = valid_by_id.get(doc_id)
        doc = docs.get(doc_id)
        if not rec or not doc:
            continue
        text = doc["text"]
        ents = rec["entities"]
        tids = set()
        for t in rec["triples"]:
            tids.add(t["head"])
            tids.add(t["tail"])

        herb_ents = [e for e in ents if e["type"] == "中药"]
        effect_ents = [e for e in ents if e["type"] == "治法功效" and e["local_id"] not in tids]

        added_this_doc = []
        for eff in effect_ents:
            idx = text.find(eff["name"])
            if idx == -1:
                continue
            # look at the span right before the effect phrase, up to the previous
            # sentence boundary, capped at 40 chars
            start = max(0, idx - 40)
            window = text[start:idx]
            boundary = max(window.rfind("。"), window.rfind("；"), window.rfind(";"))
            window = window[boundary + 1:]
            add_pos = window.rfind("加")  # last "加" before the effect phrase --
            # herbs must come from *after* this point, so a "去X" (remove) earlier in
            # the same window (e.g. "去人参，加藁本...") doesn't get misattributed the
            # effect that belongs to the added herbs.
            if add_pos == -1:
                continue  # only the "加A、B、C+功效" modifier-add pattern, not other prose
            window = window[add_pos + 1:]
            matched_herbs = [h for h in herb_ents if h["name"] in window]
            if not matched_herbs:
                continue
            for h in matched_herbs:
                added_this_doc.append({
                    "head": h["local_id"], "relation": "功效", "tail": eff["local_id"],
                    "pid": None, "kind": "relational", "flipped": False,
                })
                evidence_log.append({
                    "doc_id": doc_id, "herb": h["name"], "effect": eff["name"],
                    "quote": window + eff["name"],
                })

        if added_this_doc:
            existing_keys = {(t["head"], t["relation"], t["tail"]) for t in rec["triples"]}
            new_ones = [t for t in added_this_doc if (t["head"], t["relation"], t["tail"]) not in existing_keys]
            rec["triples"].extend(new_ones)
            if new_ones:
                n_docs_touched += 1
                n_edges_added += len(new_ones)

    write_jsonl(wd / "extraction_valid.jsonl", valid)
    write_jsonl(wd / "round7_evidence.jsonl", evidence_log)
    print(f"added {n_edges_added} 功效 edges across {n_docs_touched} docs "
          f"(out of {len(target_ids)} target docs)")
    print(f"evidence log: {wd / 'round7_evidence.jsonl'}")


if __name__ == "__main__":
    main()
