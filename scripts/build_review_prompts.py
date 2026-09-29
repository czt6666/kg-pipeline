"""Assemble per-document review material for manual (LLM-in-the-loop) extraction QA.

Takes the first N docs of a TCM split, and for each one concatenates:
  1. the entity/relation rule tables (pulled straight from schema/tcm_schema.yaml,
     same rendering as build_tcm_prompt.py so the reviewer sees exactly what the
     extractor was told),
  2. the full original text (docs.jsonl),
  3. the full extraction result (extraction_valid.jsonl -- post-validation, so
     dropped/flipped triples are already reflected).

Output is one markdown file with one section per doc, meant to be read (not
executed) by a reviewer checking for over-extraction / under-extraction / wrong
extraction. This script does not call any LLM -- it only assembles the material.
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from build_tcm_prompt import render_entity_types, render_relation_table  # noqa: E402


def read_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--split", default="neike_trial")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--out", default="docs/tcm_extraction_review_prompts.md")
    ap.add_argument("--prompt-template", default=None,
                     help="if set, use this file's rule text verbatim (everything before "
                          "the trailing 文本：{TEXT} placeholder) instead of re-rendering "
                          "from schema/tcm_schema.yaml -- keeps the review prompt byte-faithful "
                          "to whatever prompt actually produced the extraction being reviewed")
    args = ap.parse_args()

    work_dir = Path("data/work") / args.dataset / args.split
    docs = {d["doc_id"]: d for d in read_jsonl(work_dir / "docs.jsonl")}
    extractions = read_jsonl(work_dir / "extraction_valid.jsonl")[: args.n]

    if args.prompt_template:
        template_text = Path(args.prompt_template).read_text()
        rule_text = template_text.split("文本：\n{TEXT}")[0].rstrip()
        rules = f"## 抽取规则（含示例，原样摘自实际抽取用的 prompt 模板）\n\n{rule_text}\n"
    else:
        schema = yaml.safe_load(Path("schema/tcm_schema.yaml").read_text())
        entity_block = render_entity_types(schema)
        relation_table = render_relation_table(schema["relations"])

        rules = f"""## 抽取规则

### 实体类型

{entity_block}

### 关系

{relation_table}

只抽取正文明确写出的内容，不因已有医学知识补全；症状按顿号/逗号拆成独立短语；证机概要/病机等描述性语句不作为实体。
"""

    instruction = (
        "我现在在做中医知识图谱的抽取。规则、原文、结果在上面。"
        "你来评判一下有没有多抽（不该抽的抽了）、少抽（该抽的漏了）、抽错"
        "（实体归错类、关系头尾/方向错、三元组语义错），并指出原文哪一句对应哪个问题。"
    )

    sections = ["# TCM 抽取结果审阅 Prompt 集（一篇文档一条独立 prompt）\n"]

    for ex in extractions:
        doc_id = ex["doc_id"]
        doc = docs[doc_id]
        entity_lines = "\n".join(json.dumps(e, ensure_ascii=False) for e in ex["entities"])
        triple_lines = "\n".join(json.dumps(t, ensure_ascii=False) for t in ex["triples"])
        prompt = (
            f"{rules}\n"
            f"原文：\n{doc['text']}\n\n"
            f"抽取结果：\n"
            f"entities:\n{entity_lines}\n"
            f"triples:\n{triple_lines}\n\n"
            f"{instruction}"
        )
        sections.append(f"\n---\n\n## {doc_id}\n\n```\n{prompt}\n```\n")

    out_path = Path(args.out)
    out_path.write_text("\n".join(sections))
    print(f"wrote {out_path} ({len(extractions)} docs, {out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
