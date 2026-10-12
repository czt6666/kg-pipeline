# 自动构建 + 检索知识图谱流水线 — 技术方案 v4

状态：**待确认（检查点4）** — 方案确认后开始写代码。

------

## 0. 总体原则

- 唯一的 LLM 调用点是抽取；后续校验、对齐、存储、评测复原全部为确定性规则。
- 所有阈值、路径、模型名进入 `config.yaml`，代码中不出现硬编码常量。
- 图存储层的属性化是存储优化，评测层以三元组集合为唯一口径。
- 每个阶段的输出落盘为独立文件，任一阶段可从上游文件重跑而不触发 LLM 调用。

## 1. Schema

### 1.1 Schema 文件与数据集标签的关系

`resources/schemas/{dataset}.yaml` 是本项目维护的常量文件。其字段分两类：

| 字段                    | 来源       | 说明                                                         |
| ----------------------- | ---------- | ------------------------------------------------------------ |
| 实体类型集合            | 数据集官方 | DocRED 官方 NER 标签集 `{PER, ORG, LOC, TIME, NUM, MISC}`，取自 `train_annotated.json` 中 `vertexSet[*][*].type` |
| 关系 `name` / `pid`     | 数据集官方 | DocRED 官方 96 种关系，取自 `rel_info.json`（Wikidata P-id → 关系名） |
| 关系 `kind`             | 本项目标注 | `intrinsic` / `relational`，人工标注一次，依据为 range 是否为 TIME/NUM 字面量 |
| 关系 `domain` / `range` | 本项目统计 | 从 DocRED 训练集 gold 三元组统计每个关系的 (head_type, tail_type) 分布，取累计覆盖 ≥ 95% 的类型集合；统计脚本输出 `resources/schemas/{dataset}_domain_range_stats.json` 供审查 |

即：schema 文件中"实体类型能取什么值、关系能取什么名"由数据集官方标签决定，抽取时 LLM 只能在这两个集合内选择；`kind / domain / range` 是本项目为校验与存储附加的元数据，不改变标签集合本身。

### 1.2 DocRED

- 实体类型：官方 6 类，原样使用。
- 关系：官方 96 种，原样使用，`name` 取 `rel_info.json` 中的英文名，`pid` 保留用于对齐 gold。
- 抽取输出的关系名必须与 `rel_info.json` 中的名称逐字一致；校验层做一次大小写/空白归一后查表，仍不命中则丢弃。

### 1.3 GenWiki

GenWiki 无官方实体类型标签，关系为 DBpedia property，无固定枚举。处理方式：

- 实体类型：复用 DocRED 的 6 类作为抽取约束，由 LLM 在抽取时打标。评测不比较类型，仅用于 domain/range 校验和检索过滤。
- 关系：对 GenWiki 训练集三元组按 property 统计频次，取累计覆盖 ≥ 90% 的 property 进 schema，长尾不进表。抽取时不在表内的关系丢弃。覆盖率数字写入 `resources/schemas/genwiki_relation_coverage.json` 并在报告中说明。
- `kind / domain / range`：同 1.1 方法从 GenWiki 训练集统计，类型分布依赖 LLM 打标结果，因此先在 1000 篇上跑一次抽取得到类型分布再统计。

### 1.4 Schema 文件格式

```yaml
dataset: docred
entity_types: [PER, ORG, LOC, TIME, NUM, MISC]
relations:
  - name: place of birth
    pid: P19
    kind: relational
    domain: [PER]
    range: [LOC]
  - name: date of birth
    pid: P569
    kind: intrinsic
    domain: [PER]
    range: [TIME]
  - name: headquarters location
    pid: P159
    kind: relational
    domain: [ORG]
    range: [LOC]
```

### 1.5 Intrinsic / Relational 划分

仅以 `kind` 字段决定：`intrinsic` 存为 head 节点属性（值为 list），`relational` 建有向边。tail 的日期/数值正则匹配结果只写入 warning，不参与判类。

## 2. 抽取

### 2.1 输入粒度

- DocRED、GenWiki 均整篇单次调用，不分块。
- 分块仅作为超过 `config.max_input_tokens` 的 fallback：按 token 数 + 句子边界切分，重叠比例 `config.chunk_overlap`（默认 0.1）。分块结果的实体 id 加 chunk 前缀，进入文档内对齐时按 mention 规范化匹配合并。

### 2.2 输出 JSON 格式

```json
{
  "entities": [
    {"id": "e1", "name": "Marie Curie", "type": "PER", "mentions": ["Marie Curie", "She", "her"]},
    {"id": "e2", "name": "Warsaw", "type": "LOC", "mentions": ["Warsaw"]},
    {"id": "e3", "name": "1867", "type": "TIME", "mentions": ["1867"]}
  ],
  "triples": [
    {"head": "e1", "relation": "place of birth", "tail": "e2"},
    {"head": "e1", "relation": "date of birth", "tail": "e3"}
  ]
}
```

约束：

- `head` / `tail` 引用 `entities[*].id`，不写实体名。
- `name` 为文中出现的最完整字面形式；`mentions` 为该实体在文中所有出现形式（含代词），首项与 `name` 相同。
- `type` ∈ `schema.entity_types`；`relation` ∈ `schema.relations[*].name`。

### 2.3 Prompt

整段作为单条 user message 发送，无 system message，无 XML 标签。模板如下（`{...}` 为运行时填充）：

```
你是一个结构化信息抽取器。从给定文本中抽取实体和关系三元组，输出严格的 JSON。

实体类型只能取以下值：PER, ORG, LOC, TIME, NUM, MISC

关系只能取以下名称，不得自造：
{按 domain 分组列出 schema.relations[*].name，每行一条，附一句话描述}

输出规则：
1. entities 中每个实体给出 id、name、type、mentions。name 必须是文本中出现过的字面形式，取最完整的一种。mentions 列出该实体在文本中的所有出现形式，包括代词，第一项与 name 相同。
2. triples 中 head 和 tail 填写 entities 中的 id。
3. relation 必须逐字取自上方关系列表。
4. 文本中没有对应关系时不要强行生成，triples 可以少于实体数。
5. 只输出 JSON，不要任何解释，不要 markdown 代码围栏。

示例1
文本：
{few-shot 样例1 文本}
抽取结果：
{few-shot 样例1 JSON}

示例2
文本：
{few-shot 样例2 文本}
抽取结果：
{few-shot 样例2 JSON}

示例3
文本：
{few-shot 样例3 文本}
抽取结果：
{few-shot 样例3 JSON}

文本：
{待抽取文本}
抽取结果：
```

关系列表顺序固定，样例固定，以便网关 prefix cache 命中。

### 2.4 Few-shot 样例

固定 3 条，从数据集训练集选取，人工核对 JSON 与 schema 完全一致后写入 `resources/prompts/{dataset}/v*/fewshot.json`。三条样例合计覆盖：

1. 同一实体以全名、简称、代词多次出现（示范 mentions 填法）。
2. 同一文本同时含 intrinsic 与 relational 关系。
3. 方向敏感关系（如 father、subsidiary、located in the administrative territorial entity）。
4. 存在实体但无 schema 内关系的片段（示范 triples 可少）。

样例文本长度 60–120 词，输出 5–8 个实体、3–8 条三元组。

### 2.5 调用参数与容错

- `temperature=0`，`max_tokens` 按 `config.max_output_tokens`（默认 4096）；若网关支持限制 reasoning 预算则设置。
- 响应解析：`json.loads` → 失败则 `json_repair` → 仍失败则将解析错误信息附加到 prompt 末尾重试一次 → 仍失败标记 `parse_status=failed`，写入 `extraction_raw.jsonl` 后跳过。
- 缓存 key = `sha256(model + prompt + temperature + max_tokens)`，命中则不发请求。

### 2.6 溯源坐标对齐

对每个 mention 在原文中定位：精确子串匹配，多次出现按文本顺序依次分配；未命中则用 difflib `SequenceMatcher` 找最长匹配块作为 fuzzy 结果并标记 `align_method=fuzzy`；无匹配标记 `align_method=none`，保留 mention 但无坐标。

## 3. 校验层

顺序执行，所有命中写入 `warnings.jsonl`：

| 序号 | 规则                                                     | 处理               | warning 类型           |
| ---- | -------------------------------------------------------- | ------------------ | ---------------------- |
| 1    | head/tail id 不在 entities 中                            | 丢弃三元组         | `dangling_ref`         |
| 2    | type 不在 entity_types 中                                | 丢弃实体及其三元组 | `unknown_type`         |
| 3    | relation 归一后不在 schema 中                            | 丢弃三元组         | `unknown_relation`     |
| 4    | (head_type, tail_type) 不满足 domain/range，但互换后满足 | 交换 head/tail     | `flipped`              |
| 5    | 互换后仍不满足                                           | 丢弃三元组         | `type_violation`       |
| 6    | kind=intrinsic 但 tail_type ∉ {TIME, NUM}                | 保留               | `intrinsic_nonliteral` |
| 7    | kind=relational 但 tail_type ∈ {TIME, NUM}               | 保留               | `relational_literal`   |
| 8    | 同一文档内完全相同的 (head, relation, tail)              | 去重               | `duplicate`            |

## 4. 文档内对齐

作用域为单篇文档。无跨文档合并；不同文档中同名实体为不同节点。

- **Step A**：按 LLM 输出的 `entities[*].mentions` 归并，每个实体的所有 mention 指向同一 local id。
- **Step B**：规范化精确匹配。对每个实体的 `name` 与所有 mentions 做规范化：Unicode NFKC、去首尾空白、连续空白折叠为单空格、多词字符串去首冠词（a/an/the）、统一引号与连字符。同一文档内、同类型、规范化后字符串相同的实体合并。单词字符串不做大小写折叠。
- 合并用并查集实现；合并后保留 name 最长者为规范名，其余写入 `aliases`。
- 输出 `alignment_map.jsonl`：local id → canonical entity_id。
- 全局 entity_id 格式：`{doc_id}#{序号}`。

## 5. 关系去重

同一 (head, tail) 上相同 relation 去重；不同 relation 保留为多重边。不做语义融合。

## 6. 存储与中间文件

根目录 `data/`，按数据集和 split 分层。全部 jsonl 文件每行一个 JSON 对象，UTF-8，无 BOM。

```
data/
├── raw/
│   └── {dataset}/                     原始数据集，只读
├── resources/schemas/
│   ├── {dataset}.yaml          1.4 节格式
│   ├── {dataset}_domain_range_stats.json
│   └── genwiki_relation_coverage.json
├── resources/prompts/
│   ├── <dataset>/<version>/fewshot.json         [{text, output}] ×3
│   └── <dataset>/<version>/template.txt  2.3 节模板
└── work/{dataset}/{split}/
    ├── run_manifest.json
    ├── docs.jsonl
    ├── llm_cache/{sha256}.json
    ├── extraction_raw.jsonl
    ├── extraction_valid.jsonl
    ├── warnings.jsonl
    ├── mentions.jsonl
    ├── alignment_map.jsonl
    ├── nodes.jsonl
    ├── edges.jsonl
    ├── triples_eval.jsonl
    ├── graph.graphml
    ├── index/
    │   ├── nodes.faiss
    │   ├── nodes_index_map.json
    │   ├── passages.faiss
    │   └── passages_index_map.json
    └── eval/
        └── metrics.json
```

各文件定义：

**run_manifest.json** — 阶段 0 生成，每次运行覆盖

```
{run_id, dataset, split, config 快照, schema 文件 sha256, prompt 模板 sha256, fewshot sha256, git commit, 开始/结束时间, 各阶段文档数统计}
```

**docs.jsonl** — 阶段 0，从 raw 转换

```
{doc_id, text, n_tokens, chunks: [{chunk_id, char_start, char_end}] | null}
```

`chunks` 仅在触发分块时非空。

**llm_cache/{sha256}.json** — 阶段 1

```
{cache_key, model, prompt, temperature, max_tokens, response_raw, reasoning_content | null, usage, latency_ms, created_at}
```

**extraction_raw.jsonl** — 阶段 1，解析后未校验

```
{doc_id, chunk_id | null, cache_key, parse_status: ok|repaired|retried|failed, parsed: {entities, triples} | null, error | null}
```

**extraction_valid.jsonl** — 阶段 2，校验后

```
{doc_id, entities: [{local_id, name, type, mentions}], triples: [{head, relation, tail, pid, kind, flipped: bool}]}
```

**warnings.jsonl** — 阶段 2

```
{doc_id, stage, rule, payload}
```

**mentions.jsonl** — 阶段 2（溯源对齐）

```
{mention_id, doc_id, local_id, surface, char_start | null, char_end | null, align_method: exact|fuzzy|none}
```

`mention_id` 格式 `{doc_id}#m{序号}`。

**alignment_map.jsonl** — 阶段 3

```
{doc_id, local_id, entity_id}
```

**nodes.jsonl** — 阶段 4

```
{entity_id, doc_id, name, type, aliases: [str], attributes: {relation_name: [value_str]}, mention_ids: [str]}
```

**edges.jsonl** — 阶段 4

```
{edge_id, doc_id, head: entity_id, relation, pid, tail: entity_id, provenance: {head_mention_ids: [str], tail_mention_ids: [str]}}
```

**triples_eval.jsonl** — 阶段 5，评测输入

```
{doc_id, triples: [{head_name, relation, pid, tail_name, source: edge|attribute}]}
```

由 edges 直接展开 + nodes.attributes 复原得到，按 doc 聚合。评测脚本只读此文件。

**graph.graphml** — 阶段 4 导出，仅供可视化工具读取；list 类型字段序列化为 JSON 字符串存入单个属性。

**index/nodes.faiss + nodes_index_map.json** — 阶段 6 节点向量：对 `"{name} ({type}): " + 该节点参与的最多 3 条三元组线性化` 做 embedding。`nodes_index_map.json` 为 `[entity_id]` 数组，下标即 faiss 内部 id。

**index/passages.faiss + passages_index_map.json** — 阶段 6 段落向量：对 `docs.jsonl` 中每篇（或每 chunk）文本做 embedding。map 为 `[{doc_id, chunk_id}]`。

**eval/metrics.json** — 阶段 5

```
{dataset, split, run_id, n_docs, bleu, rouge, bertscore: {p, r, f1}, genres: {ts, us, fs, gs, cs}, warnings_summary: {rule: count}}
```

### 6.1 阶段与文件依赖

| 阶段        | 输入                                      | 输出                                                   |
| ----------- | ----------------------------------------- | ------------------------------------------------------ |
| 0 准备      | raw, schema, prompts, config              | run_manifest, docs.jsonl                               |
| 1 抽取      | docs.jsonl, prompt 模板, fewshot          | llm_cache, extraction_raw.jsonl                        |
| 2 校验+溯源 | extraction_raw.jsonl, schema              | extraction_valid.jsonl, warnings.jsonl, mentions.jsonl |
| 3 对齐      | extraction_valid.jsonl, mentions.jsonl    | alignment_map.jsonl                                    |
| 4 建图      | extraction_valid, alignment_map, mentions | nodes.jsonl, edges.jsonl, graph.graphml                |
| 5 评测      | nodes.jsonl, edges.jsonl, raw gold        | triples_eval.jsonl, eval/metrics.json                  |
| 6 索引      | nodes.jsonl, docs.jsonl                   | index/*                                                |

阶段 2–6 均可在不触发阶段 1 的情况下重跑。

## 7. 评测

- 评测输入固定为 `triples_eval.jsonl`，属性已复原为三元组。
- 指标脚本使用 GraphRefine 仓库原脚本，三元组序列化与分词方式与其保持一致。
- GenWiki 目标：BL-F1 ≥ 65.23，BS-F1 ≥ 85.32，GenRES-FS ≥ 98.36；DocRED 目标：BL-F1 ≥ 52.94。
- 只跑完整流水线一个配置。迭代上限 3 轮，每轮调整范围限于 prompt 措辞、few-shot 选例、schema 的 kind/domain/range 标注；未达标如实汇报。
- 每轮同时输出 `warnings_summary`，作为定位抽取错误类型的依据。

## 8. 检索

### 8.1 图搜索

1. LLM 从 query 抽取期望实体类型集合 T ⊆ entity_types、关系集合 R ⊆ relations。
2. 从语义检索命中的种子节点出发，仅沿 relation ∈ R 的边、经 type ∈ T 的节点做 BFS，跳数 `config.bfs_hops`（默认 2），扩展节点上限 `config.bfs_node_budget`（默认 500）。
3. 退化：结果为空则依次放宽 R、放宽 T。

### 8.2 语义检索

双路取并集，分别展示，不做统一排序：

- 词法：query 与节点 `name`/`aliases` 的编辑距离 Top-K。
- 语义：query embedding 对 `nodes.faiss` 与 `passages.faiss` 的 cosine Top-K。

## 9. 前端

- 原文视图：按 `mentions.jsonl` 坐标高亮，点击 mention 反查 `entity_id` 及其全部出处。
- 图谱视图：react-force-graph 渲染 nodes/edges，节点面板展示 `attributes` 与 `aliases`。
- 检索面板：图搜索与语义检索双栏。

## 10. 实施顺序

1. 阶段 0：schema.yaml（DocRED 96 关系 + 统计 domain/range）、config、prompt 模板与 3 条 few-shot。
2. 阶段 1–2：抽取 + 缓存 + 校验 + 溯源，在 20 篇上人工核对输出。
3. 阶段 3–5：对齐、建图、属性复原、接入 GraphRefine 评测脚本，得到首轮指标。
4. 阶段 6 + 检索 + 前端。
5. 按第 7 节迭代。

------

**v4 方案确认后开始写代码。**
