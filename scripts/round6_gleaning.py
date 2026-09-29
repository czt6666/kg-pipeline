"""Round 6：gleaning（用户原计划 Step 5）——对已抽取完的文档，把"一条三元组都没涉及"
的实体挑出来，连同原文再问模型一轮"这些实体在原文里有没有能建的关系，有就补，没有就
不补"，只接受能通过 schema 校验（domain/range）的新三元组，不改动已有的实体和三元组。

不是重新抽取（不会丢已有内容），是针对性补漏，天然带着原文依据（问的就是"这段原文里
这个实体的关系"，不会凭空编）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from common import read_jsonl, work_dir, write_jsonl  # noqa: E402
from llm_client import LLMClient  # noqa: E402
from stage1_extract import try_parse  # noqa: E402

RELATION_TABLE = """| relation | 头类型 | 尾类型 |
|---|---|---|
| 分型 | 疾病 | 证候 |
| 表现为 | 证候 | 症状 |
| 主症 | 疾病 | 症状 |
| 兼症 | 疾病 | 症状 |
| 治法 | 疾病 或 证候 | 治法功效 |
| 方用 | 证候 | 方剂 |
| 用药 | 证候 | 中药 |
| 病位 | 疾病 或 证候 | 脏腑经络 |
| 病因 | 疾病 或 证候 | 病因 |
| 鉴别 | 疾病 | 疾病 |
| 别名 | 疾病 | 疾病 |
| 组成 | 方剂 | 中药 |
| 功效 | 方剂 或 中药 | 治法功效 |
| 性味 | 中药 | 性味 |
| 归经 | 中药 | 脏腑经络 |
| 主治 | 中药 | 症状 / 疾病 / 证候 |"""

GLEAN_PROMPT = """你之前从下面这段中医文献里抽取了实体，但下面列出的这些实体在你的抽取结果里\
一条三元组都没有涉及（既不是任何关系的头，也不是尾）。请重新读一遍原文，只针对这些\
实体检查：原文里有没有能支持某条关系的明确陈述？有就用下面的关系表补一条三元组，没有\
就不补（不要编造、不要靠已有中医常识推断，只看这段原文字面写了什么）。

关系表（head/tail 类型必须匹配，否则不要输出）：
{RELATION_TABLE}

原文：
{TEXT}

以下实体本次抽取零关系，请逐个检查（name, type, local_id）：
{ENTITIES}

只输出 JSON：{{"triples": [{{"head": "本地id", "relation": "", "tail": "本地id"}}]}}\
——head/tail 用上面给的 local_id，relation 必须是关系表里的 16 个值之一，没有能补的就\
输出 {{"triples": []}}。不要输出解释，不要 markdown 代码围栏。"""


def build_prompt(text, unlinked):
    ent_lines = "\n".join(f"- {e['name']} ({e['type']}, id={e['local_id']})" for e in unlinked)
    return (GLEAN_PROMPT
            .replace("{RELATION_TABLE}", RELATION_TABLE)
            .replace("{TEXT}", text)
            .replace("{ENTITIES}", ent_lines))


RELATION_DEF = {
    "分型": ({"疾病", "证候"}, {"证候"}),
    "表现为": ({"证候"}, {"症状"}),
    "主症": ({"疾病"}, {"症状"}),
    "兼症": ({"疾病"}, {"症状"}),
    "治法": ({"疾病", "证候"}, {"治法功效"}),
    "方用": ({"证候"}, {"方剂"}),
    "用药": ({"证候"}, {"中药"}),
    "病位": ({"疾病", "证候"}, {"脏腑经络"}),
    "病因": ({"疾病", "证候"}, {"病因"}),
    "鉴别": ({"疾病"}, {"疾病"}),
    "别名": ({"疾病"}, {"疾病"}),
    "组成": ({"方剂"}, {"中药"}),
    "功效": ({"方剂", "中药"}, {"治法功效"}),
    "性味": ({"中药"}, {"性味"}),
    "归经": ({"中药"}, {"脏腑经络"}),
    "主治": ({"中药"}, {"症状", "疾病", "证候"}),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--doc-ids", required=True, help="json file: list of doc_id")
    ap.add_argument("--max-tokens", type=int, default=4096)
    args = ap.parse_args()

    wd = work_dir("TCM", args.split)
    target_ids = set(json.load(open(args.doc_ids, encoding="utf-8")))

    docs = {d["doc_id"]: d for d in read_jsonl(wd / "docs.jsonl")}
    valid = list(read_jsonl(wd / "extraction_valid.jsonl"))
    valid_by_id = {r["doc_id"]: r for r in valid}

    client = LLMClient(wd / "llm_cache")

    n_added = 0
    n_docs_touched = 0
    for doc_id in sorted(target_ids):
        rec = valid_by_id.get(doc_id)
        doc = docs.get(doc_id)
        if not rec or not doc:
            continue
        tids = set()
        for t in rec["triples"]:
            tids.add(t["head"])
            tids.add(t["tail"])
        unlinked = [e for e in rec["entities"] if e["local_id"] not in tids]
        if not unlinked:
            continue

        prompt = build_prompt(doc["text"], unlinked)
        record = client.chat(prompt, max_tokens=args.max_tokens)
        parsed, status, err = try_parse(record["response_raw"])
        if not parsed or "triples" not in parsed:
            continue

        ent_by_id = {e["local_id"]: e for e in rec["entities"]}
        accepted = []
        for t in parsed["triples"]:
            head, tail, rel = t.get("head"), t.get("tail"), t.get("relation")
            if head not in ent_by_id or tail not in ent_by_id or rel not in RELATION_DEF:
                continue
            domain, range_ = RELATION_DEF[rel]
            ht, tt = ent_by_id[head]["type"], ent_by_id[tail]["type"]
            if ht in domain and tt in range_:
                accepted.append({"head": head, "relation": rel, "tail": tail, "pid": None, "kind": "relational", "flipped": False})
            elif tt in domain and ht in range_:
                accepted.append({"head": tail, "relation": rel, "tail": head, "pid": None, "kind": "relational", "flipped": True})

        if accepted:
            existing_keys = {(t["head"], t["relation"], t["tail"]) for t in rec["triples"]}
            new_ones = [t for t in accepted if (t["head"], t["relation"], t["tail"]) not in existing_keys]
            rec["triples"].extend(new_ones)
            n_added += len(new_ones)
            if new_ones:
                n_docs_touched += 1

    write_jsonl(wd / "extraction_valid.jsonl", valid)
    print(f"gleaning done: {n_added} new triples added across {n_docs_touched} docs "
          f"(out of {len(target_ids)} target docs)")


if __name__ == "__main__":
    main()
