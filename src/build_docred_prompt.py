"""Stage 0: render prompts/docred_prompt_template.txt from schema + fewshot (DESIGN.md 2.3).

The relation list and few-shot examples are baked into the template file as static text
(not re-rendered per request) so that the prompt prefix is byte-identical across calls,
which is what DESIGN.md 2.3 means by "关系列表顺序固定，样例固定，以便网关 prefix cache 命中".
The only remaining runtime placeholder is {{TEXT}}.
"""
import json
from collections import defaultdict
from pathlib import Path

import yaml

SCHEMA_PATH = Path("schema/docred_schema.yaml")
FEWSHOT_PATH = Path("prompts/docred_fewshot.json")
OUT_PATH = Path("prompts/docred_prompt_template.txt")


def render_relation_list(relations):
    groups = defaultdict(list)
    for r in relations:
        key = tuple(r["domain"]) if r["domain"] else ("ANY",)
        groups[key].append(r)
    lines = []
    for domain_key in sorted(groups.keys()):
        lines.append(f"[{' / '.join(domain_key)} 作为主语时可用]")
        for r in sorted(groups[domain_key], key=lambda r: r["name"]):
            lines.append(f"- {r['name']} — {r['description']}")
    return "\n".join(lines)


def render_fewshot(examples):
    blocks = []
    for i, ex in enumerate(examples, 1):
        output_json = json.dumps(ex["output"], ensure_ascii=False)
        blocks.append(f"示例{i}\n文本：\n{ex['text']}\n抽取结果：\n{output_json}")
    return "\n\n".join(blocks)


def main():
    schema = yaml.safe_load(SCHEMA_PATH.read_text())
    fewshot = json.loads(FEWSHOT_PATH.read_text())

    entity_types = ", ".join(schema["entity_types"])
    relation_list = render_relation_list(schema["relations"])
    fewshot_block = render_fewshot(fewshot)

    template = f"""你是一个结构化信息抽取器。从给定文本中抽取实体和关系三元组，输出严格的 JSON。

实体类型只能取以下值：{entity_types}

关系只能取以下名称，不得自造（按主语类型分组列出，每行一条附一句话说明）：
{relation_list}

输出规则：
1. entities 中每个实体给出 id、name、type、mentions。name 必须是文本中出现过的字面形式，取最完整的一种。mentions 列出该实体在文本中的所有出现形式，包括代词，第一项与 name 相同。
2. triples 中 head 和 tail 填写 entities 中的 id。
3. relation 必须逐字取自上方关系列表。
4. 文本中没有对应关系时不要强行生成，triples 可以少于实体数。
5. 只输出 JSON，不要任何解释，不要 markdown 代码围栏。

{fewshot_block}

文本：
{{TEXT}}
抽取结果：
"""

    OUT_PATH.write_text(template)
    print(f"wrote {OUT_PATH} ({len(template)} chars, ~{len(template)//4} tokens est.)")


if __name__ == "__main__":
    main()
