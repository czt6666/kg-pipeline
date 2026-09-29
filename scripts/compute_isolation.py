"""计算融合图的孤立率：整体、按类型、度最高的 20 个节点。

用法：
    .venv/bin/python scripts/compute_isolation.py data/work/TCM/merged_neike_v1_boundaryfix
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
    exclude_quarantined = "--exclude-quarantined" in sys.argv
    nodes = load_jsonl(merged_dir / "nodes.jsonl")
    edges = load_jsonl(merged_dir / "edges.jsonl")

    if exclude_quarantined:
        nodes = [n for n in nodes if not n.get("quarantined")]

    degree = Counter()
    for e in edges:
        degree[e["head"]] += 1
        degree[e["tail"]] += 1

    by_type_total = Counter()
    by_type_isolated = Counter()
    for n in nodes:
        t = n["type"]
        by_type_total[t] += 1
        if degree[n["entity_id"]] == 0:
            by_type_isolated[t] += 1

    total = len(nodes)
    isolated = sum(by_type_isolated.values())

    print(f"=== {merged_dir.name} {'(不含隔离区)' if exclude_quarantined else ''} ===")
    print(f"总节点数: {total}  总边数: {len(edges)}")
    print(f"整体孤立率: {isolated}/{total} = {isolated/total:.4%}")
    print()
    print("按类型孤立率:")
    for t in sorted(by_type_total, key=lambda t: -by_type_isolated[t]):
        n = by_type_total[t]
        iso = by_type_isolated[t]
        print(f"  {t:8s} {iso:5d}/{n:5d} = {iso/n:.2%}")
    print()

    name_by_id = {n["entity_id"]: (n["name"], n["type"]) for n in nodes}
    print("度最高的 20 个节点:")
    for eid, d in degree.most_common(20):
        name, t = name_by_id.get(eid, ("?", "?"))
        print(f"  {d:5d}  {name} ({t})")


if __name__ == "__main__":
    main()
