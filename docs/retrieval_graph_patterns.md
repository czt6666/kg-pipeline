# Graph Pattern 检索设计

状态：**待 review**。本文档只定义 pattern 目录和执行策略，不涉及实现；review 通过后再写
`src/retrieval/graph_patterns.py`。

## 1. 背景与目标

现有 `retrieval.graph_search`（原 `src/retrieval.py`，现 `src/retrieval/basic.py`）是无约束
的 N-hop BFS：给定种子节点，沿任意关系扩展，靠 `relations`/`types` 白名单和 `node_budget`
兜底。这对"探索图谱"这类交互式场景够用，但对"给一个专业名词，要精确、可解释的结构化事实"
这个新场景不够——BFS 展开出来的一堆节点里哪些是"回答问题的核心事实"、哪些是路过的噪声，
没有区分。

Graph Pattern 检索要做的是：针对已经由 lexical/semantic 解析出的种子实体（带 `type`），
按 schema 的语义（哪个关系接哪个关系在临床上是一句完整的话）跑**预先设计好、有方向、有终点
类型**的查询，而不是无约束展开。每次命中都能直接对应一句人话（"疾病 X 分型为证候 Y，
治法为 Z"），这也是它和 BFS 的本质区别、以及为什么值得单独设计而不是复用 `graph_search`。

## 2. 两类 pattern

### 2.1 Profile pattern（单跳画像）—— 任何种子都跑

不管种子是什么类型，默认跑一次：以种子为 head 的所有出边（按 relation 分组）+ 以种子为
tail 的所有入边（按 relation 分组），相当于一张结构化"实体卡片"。这一层保证**任何**能被
lexical/semantic 定位到的实体，哪怕不在下面 2.2 的命名 pattern 覆盖范围内，也至少有一份
完整的直接关系可用。

性味这类 `kind: intrinsic` 关系已经在 stage4 折成了节点的 `attributes` 字段，不是边，
profile pattern 直接读 `node["attributes"]`，一并纳入画像。

### 2.2 Compound pattern（命名多跳）—— 按种子类型枚举

单跳画像回答不了"这个病怎么治""这味药最终治什么病"这类需要跨 2-4 跳的问题。这类问题在
schema 里的跳法是固定的（受 domain/range 约束），值得预先命名、固定跳法，而不是每次现场
BFS 猜。

初版只给 5 种最常被直接查询的实体类型设计命名 pattern：**疾病、证候、症状、中药、方剂**。
其余 4 类（病因、治法功效、性味、脏腑经络）是链路中的中间节点，直接查询它们的场景较少，
只吃 profile pattern，不单独设计命名 pattern（这条在第 8 节列为待确认项）。

## 3. Pattern 目录

方向记号：`A --r--> B` 表示 A 是 head、B 是 tail；`A <--r-- B` 表示 A 是 tail、B 是 head
（种子在前）。带 `*` 的关系必须把 `condition` 字段带出。

### 疾病

| id | 跳法 | 说明 | 对应 eval 类型 |
|---|---|---|---|
| P-DISEASE-SYNDROMES | 疾病 --分型--> 证候 | 该病都有哪些证型 | 病→证型列表 |
| P-DISEASE-TREATMENT | 疾病 --分型--> 证候 --治法--> 治法功效 | 分证型给出治法 | 病→证型列表 + 证型→治法 |
| P-DISEASE-FORMULAS | 疾病 --分型--> 证候 --方用--> 方剂 | 分证型给出主方 | 病→证型列表 + 证型→主方 |
| P-DISEASE-FULL-CHAIN | 疾病 --分型--> 证候 --方用--> 方剂 --组成--> 中药 | 完整治疗链（病→证→方→药） | 三类拼接，最深一条 |
| P-DISEASE-ETIOLOGY | 疾病 --病因--> 病因（可递归到病因，深度上限见第4节） | 病因/病因链 | 无 |
| P-DISEASE-LOCATION | 疾病 --病位--> 脏腑经络 | 病位 | 无 |
| P-DISEASE-MAIN-SYMPTOMS | 疾病 --主症/兼症--> 症状 | 诊断学总-分写法的主症/兼症 | 无 |
| P-DISEASE-DIFFERENTIAL | 疾病 --鉴别--> 疾病（双向查，见第4节） | 鉴别诊断 | 无 |
| P-DISEASE-ALIAS | 疾病 --别名--> 疾病（双向查） | 别称 | 无 |

### 证候（图里的枢纽类型，21 个关系里近一半以它为 domain）

| id | 跳法 | 说明 | 对应 eval 类型 |
|---|---|---|---|
| P-SYNDROME-PARENT | 证候 <--分型-- 疾病 | 反查这个证候属于哪个病 | 无（是"病→证型列表"的反向） |
| P-SYNDROME-FULL-TX | 证候 --治法--> 治法功效；证候 --方用--> 方剂 --组成--> 中药；证候 --用药--> 中药 | 完整治疗方案（分支型，不是单链） | 证型→治法 + 证型→主方 |
| P-SYNDROME-MODIFIERS* | 证候 --加药/减药/加方/换方(*)--> …；证候 --变证--> 子证候（递归深度上限见第4节，子证候再套一层 profile） | 随证加减链 | 无 |
| P-SYNDROME-DIFFERENTIAL | 证候 --鉴别--> 证候（双向查） | 鉴别诊断 | 无 |

（"证型→症状"即 `表现为` 关系，已被 profile pattern 覆盖，不重复设 compound。）

### 症状（多数场景是反查——症状在很多关系的 range 里）

| id | 跳法 | 说明 | 对应 eval 类型 |
|---|---|---|---|
| P-SYMPTOM-TO-SYNDROME | 症状 <--表现为-- 证候 | 这个症状对应哪些证型 | **症状→证型**（核心场景） |
| P-SYMPTOM-TO-DISEASE | 症状 <--表现为-- 证候 <--分型-- 疾病 | 再反查到病 | 症状→证型 的延伸 |
| P-SYMPTOM-AS-MAIN | 症状 <--主症/兼症-- 疾病 | 这个症状是哪些病的主症/兼症 | 无 |
| P-SYMPTOM-AS-EFFECT | 症状 <--病因-- {疾病,证候,病因} | 反查"什么病因会导致这个症状"（schema 允许病因的 range 含症状） | 无 |
| P-SYMPTOM-TREATED-BY | 症状 <--主治-- 中药 | 治这个症状的中药 | 无 |
| P-SYMPTOM-TREATMENT | 症状 <--表现为-- 证候 --治法/方用--> …；症状 <--主症/兼症-- 疾病 --分型--> 证候 --治法/方用--> … | 症状本身没有治法/方用边（schema 里挂在疾病/证候上），反查回最近的证候/疾病再顺着治疗边走一步，否则"便秘""失眠"这类直接以症状命中的查询会查不到治疗方法 | 无 |

### 中药

| id | 跳法 | 说明 | 对应 eval 类型 |
|---|---|---|---|
| P-HERB-PROFILE | 中药 --性味(属性)/归经/功效/主治--> … | 性味归经功效主治画像 | 无（profile 已含，这里是精选展示顺序） |
| P-HERB-IN-FORMULA | 中药 <--组成-- 方剂 | 这味药用在哪些方剂 | 无 |
| P-HERB-FOR-SYNDROME | 中药 <--用药/加药/减药(*)-- 证候 | 这味药用于哪些证候（含随证加减） | 无 |
| P-HERB-TO-DISEASE | 中药 <--组成-- 方剂 <--方用-- 证候 <--分型-- 疾病 | 反查最终治什么病（3 跳，最深的反查链） | 无 |

### 方剂

| id | 跳法 | 说明 | 对应 eval 类型 |
|---|---|---|---|
| P-FORMULA-COMPOSITION | 方剂 --组成--> 中药 | 组成 | 无 |
| P-FORMULA-INDICATION | 方剂 <--方用/加方/换方(*)-- 证候 | 主治证型 | **方→主治证型** |
| P-FORMULA-TO-DISEASE | 方剂 <--方用-- 证候 <--分型-- 疾病 | 反查主治的病 | 方→主治证型 的延伸 |

## 4. 执行策略

- **每跳扇出上限 30**：按 `merged_neike/stats.json` 的平均度数（如 用药 3086 边 / 816 个
  证候 ≈ 3.8）留了充足冗余，超过上限按边在原文出现的文档数/字典序截断，不做加权采样。
- **对称关系双向查找**：`鉴别`、`别名` 只存一条边（"三者同属"这种只记一次），种子若落在
  `tail` 侧也要能查到——profile pattern 和涉及这两个关系的 compound pattern 都对
  head/tail 各查一次再合并去重。
- **递归深度上限 2**：`病因→病因`（连锁病机）和 `证候→变证→证候`（母子证候）都可能再往下
  一层（子证候本身也可能再变证），上限设 2 层防止链路失控；超过上限的边直接丢弃、不报错。
- **边去重**：同一 `(head, relation, tail)` 只保留一条（合并图里可能因为多篇文档来源产生
  重复边，`source_doc_ids` 已经在 stage7_merge 里合并过，这里只是防御性去重）。
- **不做"必须命中几条 pattern 才算有效"的门槛**：种子类型落在第 2.2 节覆盖的 5 类之外，
  或者命中的 compound pattern 为空，都只返回 profile 画像，不算错误。

## 5. 输出数据结构

每个 pattern 命中产出一条或多条 **path**（多分支的 pattern，如 P-DISEASE-TREATMENT 对每个
证候各出一条 path，不合并成树）：

```json
{
  "pattern_id": "P-DISEASE-TREATMENT",
  "seed_entity_id": "m#123",
  "hops": [
    {"head": "m#123", "relation": "分型", "tail": "m#456", "condition": null},
    {"head": "m#456", "relation": "治法", "tail": "m#789", "condition": null}
  ],
  "end_entity_id": "m#789"
}
```

`hops` 是按 schema 真实方向记录的（不因为查询方向是反查就翻转 head/tail），
`present.py` 生成文字时自己判断种子在每一跳里是 head 还是 tail 来组织语序。这份结构直接
喂给 fusion（按 pattern 命中数/end_entity 打分排序）和 present（模板转文字），
不需要额外转换。

## 6. 与现有 eval 分类的覆盖关系

`eval/questions.jsonl` 的 5 类问题被以下 pattern 直接覆盖：

| eval 问题类型 | 覆盖 pattern |
|---|---|
| 症状→证型 | P-SYMPTOM-TO-SYNDROME |
| 证型→治法 | profile（`治法`）/ P-SYNDROME-FULL-TX |
| 证型→主方 | profile（`方用`）/ P-SYNDROME-FULL-TX |
| 方→主治证型 | P-FORMULA-INDICATION |
| 病→证型列表 | P-DISEASE-SYNDROMES |

其余 pattern（中药画像/反查、随证加减链、鉴别诊断、病因链等）是 schema 支持但现有 100 题
评测集没覆盖到的场景，属于这次新增的能力。

## 7. 开放问题（需要确认）

1. 每跳扇出上限 30——够不够？如果某些证候的"用药"边实际比预期多很多，是要提高上限还是
   接受截断（毕竟后面还有 topK 和融合排序会再筛一轮）。
2. `病因→病因`、`变证` 递归深度上限 2——是否需要更深（比如三代母子证候链）？
3. 病因/治法功效/性味/脏腑经络 这 4 类中间节点不设命名 compound pattern、只给 profile——
   同意吗，还是有具体场景需要给某一类也设计专门的查询链（比如直接查"肺"这个脏腑经络，
   想要的是"哪些证候病位在肺"这种反查）？
4. `P-DISEASE-FULL-CHAIN`/`P-HERB-TO-DISEASE` 这种 3-4 跳最深链，分支相乘可能条数不少
   （比如一个病 5 个证型、每个证型 2 个方、每个方 8 味药 = 80 条 path），是在 pattern 层
   就做展示条数上限，还是完全交给后面的融合排序 + topK 截断？
