"""Stage 0 (TCM): render prompts/tcm_prompt_template.txt from schema + fewshot.

Same rationale as build_docred_prompt.py: the prompt prefix should be byte-identical
across calls (gateway prefix-cache friendly), so entity/relation text and the few-shot
example are baked in as static text rather than re-rendered per request. The only
runtime placeholder is {TEXT}.

Unlike docred/genwiki (flat entity-type list, grouped-bullet relation list), the TCM
schema carries richer per-type prompt text (prompt_line) and a markdown relation table
(with a "常见文本线索" cues column) -- this generalizes across multiple TCM document
genres (教材/方书/本草/医论), not just one disease-entry textbook layout.
"""
import json
from pathlib import Path

import yaml

SCHEMA_PATH = Path("schema/tcm_schema.yaml")
FEWSHOT_PATH = Path("prompts/tcm_fewshot.json")
OUT_PATH = Path("prompts/tcm_prompt_template.txt")


def render_entity_types(schema):
    lines = []
    for e in schema["entity_types"]:
        lines.append(f"- {e['name']}：{e['prompt_line']}")
    return "\n".join(lines)


def render_relation_table(relations):
    lines = ["| relation | 头类型 | 尾类型 | 含义 | 常见文本线索 |", "|---|---|---|---|---|"]
    for r in relations:
        domain = " 或 ".join(r["domain"])
        rng = " / ".join(r["range"])
        lines.append(f"| {r['name']} | {domain} | {rng} | {r['description']} | {r['cues']} |")
    return "\n".join(lines)


def render_fewshot(examples):
    blocks = []
    for ex in examples:
        output_json = json.dumps(ex["output"], ensure_ascii=False, separators=(",", ":"))
        blocks.append(f"文本：\n{ex['text']}\n\n抽取结果：\n{output_json}")
    return "\n\n".join(blocks)


def main():
    schema = yaml.safe_load(SCHEMA_PATH.read_text())
    fewshot = json.loads(FEWSHOT_PATH.read_text())

    n_types = len(schema["entity_types"])
    n_rels = len(schema["relations"])
    entity_block = render_entity_types(schema)
    relation_table = render_relation_table(schema["relations"])
    fewshot_block = render_fewshot(fewshot)

    template = f"""你是一个中医药文献结构化信息抽取器。从给定的中医文献正文片段（教材、方书、本草、医论等）中抽取实体和关系三元组，输出严格的 JSON。

## 一、实体类型（type 只能取以下 {n_types} 个值）

{entity_block}

## 二、关系（relation 只能取以下 {n_rels} 个值，头尾类型必须匹配）

{relation_table}

不同文献只会涉及其中一部分关系（教材以前 7 条为主，本草以后 5 条为主），只抽取正文明确写出的，不要为了凑关系而生成。

## 三、输出格式

{{
  "entities": [
    {{"id": "e1", "name": "", "type": "", "mentions": [""]}}
  ],
  "triples": [
    {{"head": "e1", "relation": "", "tail": "e2"}}
  ]
}}

## 四、输出规则

1. name 必须是文本中出现过的字面形式，取最完整的一种；mentions 列出该实体在文本中的所有出现形式，第一项与 name 相同。同一实体只出现一次，多处提及合并到 mentions。
2. 症状按顿号、逗号拆成独立短语，每个短语一个实体："舌质淡，苔白，脉迟缓" → 舌质淡、苔白、脉迟缓 三个实体。不要把整段临床表现合成一个实体，也不要拆到短语以下（"苔白"不拆成"苔"和"白"）。
3. 证机概要、病机、病因等描述性语句不作为实体，不生成三元组。
4. 方剂 name 去掉"加减""化裁""合方"等后缀："麻黄汤加减"的 name 为麻黄汤，mentions 同时包含"麻黄汤加减"。"随证加减""若……加……"中提到的药物不生成"组成"关系。
5. 关系方向固定，不输出反向三元组：方剂对证候的"主治"一律表示为 证候 方用 方剂。
6. 头尾类型与关系表不符的三元组不输出。文本中没有明确写出的关系不推断、不补全：正文未列出方剂组成时不凭已有知识补药物，未写病位时不生成"病位"关系。
7. 忽略【医案】【病例】等示例中的患者姓名、性别、年龄、就诊日期等病历信息，不抽取其中的实体和关系。
8. 只输出 JSON，不要解释，不要 markdown 代码围栏。

## 五、示例

{fewshot_block}

文本：
{{TEXT}}

抽取结果：
"""

    OUT_PATH.write_text(template)
    print(f"wrote {OUT_PATH} ({len(template)} chars, ~{len(template)//4} tokens est.)")


if __name__ == "__main__":
    main()
