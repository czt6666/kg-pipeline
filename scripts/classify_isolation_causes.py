"""对 merged 图里的孤立节点做根因分类。

对每个孤立节点，回到其 source_doc_ids 对应的单文档 extraction_valid.jsonl，
按 name+type 找到该文档里的本地实体 local_id，再查三样东西：
  1. parse_status 是否 != ok（截断/修复问题）
  2. local_id 是否只出现在该文档 modifiers.jsonl 的
     condition_symptoms/add/remove 里（随证加减设计性孤立）
  3. 除以上两种情况外的「未知」——需要人工抽样再看（上下文缺失/模型漏建等）

一个节点可能横跨多篇文档，只要有一篇文档的这个实体不满足"仅出现在modifiers"，
就不能整体归为"modifiers 设计性孤立"（因为另一篇文档里这个实体本该正常建边却没建）。
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    merged_dir = Path(sys.argv[1])
    split_dir = Path(sys.argv[2])  # e.g. data/work/TCM/neike_v1_boundaryfix

    nodes = load_jsonl(merged_dir / "nodes.jsonl")
    edges = load_jsonl(merged_dir / "edges.jsonl")
    deg = Counter()
    for e in edges:
        deg[e["head"]] += 1
        deg[e["tail"]] += 1
    isolated = [n for n in nodes if deg[n["entity_id"]] == 0]
    print(f"孤立节点总数: {len(isolated)}")

    raw = load_jsonl(split_dir / "extraction_raw.jsonl")
    status_by_doc = {r["doc_id"]: r.get("parse_status") for r in raw}

    valid = load_jsonl(split_dir / "extraction_valid.jsonl")
    valid_by_doc = {r["doc_id"]: r for r in valid}

    mods = load_jsonl(split_dir / "modifiers.jsonl")
    mod_ids_by_doc = {}
    for m in mods:
        ids = set()
        for mm in m.get("modifiers", []):
            ids.update(mm.get("condition_symptoms", []))
            ids.update(mm.get("add", []))
            ids.update(mm.get("remove", []))
        mod_ids_by_doc[m["doc_id"]] = ids

    cause = Counter()
    examples = defaultdict(list)

    for n in isolated:
        docs = n["source_doc_ids"]
        statuses = set(status_by_doc.get(d) for d in docs)
        bad_status = statuses - {"ok"}
        all_bad = "ok" not in statuses

        # for each doc, find local entities matching name+type, check modifiers-only
        modifiers_only_everywhere = True
        found_any_local = False
        for d in docs:
            rec = valid_by_doc.get(d)
            if not rec:
                continue
            mod_ids = mod_ids_by_doc.get(d, set())
            local_matches = [e["local_id"] for e in rec["entities"]
                              if e["name"] == n["name"] and e["type"] == n["type"]]
            for lid in local_matches:
                found_any_local = True
                if lid not in mod_ids:
                    modifiers_only_everywhere = False

        if all_bad:
            c = "parse_status_bad_only"
        elif modifiers_only_everywhere and found_any_local:
            c = "modifiers_only"
        elif bad_status:
            c = "mixed_bad_and_ok_status"
        else:
            c = "unknown_ok_status"
        cause[c] += 1
        if len(examples[c]) < 6:
            examples[c].append((n["name"], n["type"], docs[:2]))

    print()
    for c, n in cause.most_common():
        print(f"{c}: {n} ({n/len(isolated):.1%})")
        for name, t, docs in examples[c]:
            print(f"    {name} ({t})  {docs}")


if __name__ == "__main__":
    main()
