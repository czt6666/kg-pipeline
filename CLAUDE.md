# CLAUDE.md

## 硬性规则

- `prompts/{dataset}_prompt_template.txt` 是生成物，不手改——改 `schema/{dataset}_schema.yaml`
  或 `{dataset}_fewshot.json` 后跑 `src/build_{dataset}_prompt.py` 重新渲染，保证同一 schema
  永远生成同一段 prompt（网关 prefix cache 依赖这点）。
- 新数据集 / schema 改动后，`stage1_extract` 大批量跑之前先把渲染好的 prompt 拿给用户确认。
- 批量 OCR 不用 LLM 视觉模型，扫描版 PDF 走 `src/stage0_ocr.py`（本地 macOS Vision 框架）。
- `data/raw/` 只读。它和 `data/cache/` 已 gitignore，`data/work/` 没有——`git add` 前想清楚要不要
  把 `llm_cache/`、`*.faiss` 这类大文件带进仓库。

## 重要目录讲解

```
data/raw/{dataset}/               原始语料，只读
schema/{dataset}_schema.yaml      实体/关系定义唯一来源（entity_types 支持纯字符串或
                                   {name, prompt_line} 对象两种格式，见 stage2_validate.load_schema）
prompts/{dataset}_fewshot.json    few-shot 样例，人工撰写
prompts/{dataset}_prompt_template.txt  生成物
src/build_{dataset}_prompt.py     schema+fewshot → prompt_template.txt 渲染脚本
src/stage0~stage7                 流水线各阶段；除 stage0 OCR、stage1 抽取、stage6 embedding
                                   外均不触网，可反复重跑
data/work/{dataset}/{split}/      单个 split 的中间产物
data/work/{dataset}/merged/       stage7 跨文档合并图，可视化"完整知识图谱"读这里
web/ (Vite+React, src/serve.py 提供 API)  按文件契约动态发现数据集，新数据集产出同名
                                   文件即自动出现，无需改代码；进入合并视图需另跑
                                   stage7_merge.py。前端改完要 `npm run build`（在 web/
                                   下）产出 web/dist/，serve.py 只读 dist/，不读 src/
```

## Data中间数据讲解

除 `index/*.faiss`（可重新生成）外都不要手删——是排查抽取质量的唯一依据：

| 文件 | 作用 |
|---|---|
| `docs.jsonl` | 抽取输入真相来源；分段最易出 bug，留着才能复现 |
| `llm_cache/{sha256}.json` | 阶段1磁盘缓存，见下节 |
| `extraction_raw.jsonl` | 模型原始解析结果，查"模型吐了什么"不必重新调用 |
| `extraction_valid.jsonl` / `warnings.jsonl` | 校验结果 + 三元组被丢弃的原因；判断质量先看 warnings |
| `mentions.jsonl` | 实体→原文字符坐标，前端出处/反查功能依赖 |
| `alignment_map.jsonl` | 文档内 local_id → 全局 entity_id 的合并记录 |
| `nodes.jsonl` / `edges.jsonl` / `graph.graphml` | 单文档图谱，评测与索引的直接输入 |
| `merged/*` | stage7 产物，"完整知识图谱"唯一数据源；`source_doc_ids` 是"来源分析"的基础，不能丢 |

### llm_cache目录

- key = `sha256(model + 完整prompt + temperature + max_tokens)`，不含 doc_id，文本相同即共享缓存。
- 命中直接读盘；改 prompt/schema 后重跑自然打出新 key，无需手动清缓存。
- 想强制重跑：删对应 `{key}.json`，或删整个 `llm_cache/`（更省事但会重打所有请求）。
- 文件是明文 JSON（完整 prompt + 模型回复，不含密钥），可直接打开排查。

## Schema 设计

- `kind: intrinsic` 挂成头实体 `attributes` 里的字符串（字面量尾实体）；`relational` 才是图里的边。
- `domain`/`range` 是硬约束：类型不符会被丢弃（`type_violation`），头尾颠倒但类型对得上会自动
  翻转（`flipped`）。某关系被系统性丢弃较多时，先找用户确认要放宽约束还是接受丢弃，不要擅自改。
