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
data/work/{dataset}/merged*/      stage7 跨文档合并图，可视化"完整知识图谱"读这里；一个
                                   dataset 下可以有多个独立合并图（目录名任意，默认
                                   `merged`），如 TCM 的 merged_neike/merged_jichu/
                                   merged_zhenduan——每本书各自合并一张图，互不跨书合并
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
| `modifiers.jsonl` | TCM 专属，随证加减（v2_pro prompt 起才有），按 doc_id 存 head/condition/add/remove；不进 nodes/edges 图 |
| `mentions.jsonl` | 实体→原文字符坐标，前端出处/反查功能依赖 |
| `alignment_map.jsonl` | 文档内 local_id → 全局 entity_id 的合并记录 |
| `nodes.jsonl` / `edges.jsonl` / `graph.graphml` | 单文档图谱，评测与索引的直接输入 |
| `merged*/*` | stage7 产物（`--out` 决定目录名），"完整知识图谱"唯一数据源；`source_doc_ids` 是"来源分析"的基础，不能丢 |

### llm_cache目录

- key = `sha256(model + 完整prompt + temperature + max_tokens)`，不含 doc_id，文本相同即共享缓存。
- 命中直接读盘；改 prompt/schema 后重跑自然打出新 key，无需手动清缓存。
- 想强制重跑：删对应 `{key}.json`，或删整个 `llm_cache/`（更省事但会重打所有请求）。
- 文件是明文 JSON（完整 prompt + 模型回复，不含密钥），可直接打开排查。

## TCM 多书全量抽取（neike/jichu/zhenduan）

`data/raw/TCM/` 下三本扫描版教材各自全量跑通 stage0→stage6，分别对应 dataset=TCM 的
`neike`/`jichu`/`zhenduan` 三个 split（书与书之间不跨文档合并，各自 stage7_merge 出
独立的 `merged_{split}/`，不是同一张图）：

| split | 源文件 | 内容页范围（0-based，含首尾） | 分段脚本 |
|---|---|---|---|
| `neike`（中医内科学） | 中医内科学教材.pdf | 上篇总论 20-65 + 下篇各论 66-450（451+ 是"教材目录"丛书页，跳过） | 20-65 用 `build_tcm_generic.py`，66-450 用 `build_tcm.py`，两次输出（`--out docs_zonglun.jsonl` / `docs_gelun.jsonl`）按 doc_id 前缀 `tcm_neike_zonglun_`/`tcm_neike_gelun_` 区分后拼进同一个 `docs.jsonl` |
| `jichu`（中医基础理论） | 中医药版-中医基础理论.pdf | 18-238 | `build_tcm_generic.py` 一次跑完（含开头"绪论"，无 zonglun/gelun 之分） |
| `zhenduan`（中医诊断学） | 中医诊断学.pdf | 16-226 | 同上 |

页范围是翻书样本人工定的（跳过封面/编委会/前言/目录等前置页，跳过书后"教材目录"丛书
广告页），换书或换版本要重新抽样确认，不能照搬。

### 两种分段脚本，什么时候用哪个

- `build_tcm.py`：按【辨证论治】【病因病机】等方括号小节 + `第X节 疾病名` 边界切，是给
  中医内科学"一节一病"的下篇各论体例写的，只对这种版式管用。
- `build_tcm_generic.py`：按 `第X章`（章号独占一行，标题在下一行）+ `第X节`/`一、二、三、`
  枚举号切，章内还嵌套不到就再用 `（一）（二）（三）` 兜底、最后按空行段落硬包大小上限
  （`MAX_CHUNK_CHARS=1800`）。给中医基础理论/中医诊断学这类"章-节-一二三"层级教材用，
  也是中医内科学"上篇总论"（第一~三章，非疾病条目体例）该用的。
- 两者共用 `build_tcm.py` 里的 OCR 清洗（`load_pages`/`smart_join`/`strip_figure_blocks`），
  `load_pages(wd, start_page, end_page)` 支持按页范围过滤，同一个 split 的 `ocr_pages.jsonl`
  可以被切两刀分别喂给两种分段器（neike 的 zonglun/gelun 就是这么做的）。
- 调试分段：两个脚本的 `--out` 参数可以把结果写到非 `docs.jsonl` 的文件名（配合
  `--start-page`/`--end-page`/`--doc-prefix`），不会覆盖已跑通的正式 `docs.jsonl`，可以
  先对一段页码范围试跑、人工看 chunk 标题/大小/原文是否合理，满意了再正式跑全书。

### 全量跑之前先用采样 trial 检查 schema 适配度

新书的行文体例和实体分布可能和已验证过的书差很远（比如"证候→证候鉴别""病因→病因"
连锁病机描述，这些在纯疾病条目体例的书里不会出现）。先建一个按章节跨度抽样（不是只取
前 N 篇，会全在同一章）的小 split 跑 stage1+stage2，看 `warnings.jsonl` 里
`type_violation` 是不是集中在少数几种 `(relation, head_type, tail_type)` 组合上——
集中就说明是 schema 域/值域没覆盖到、值得参照下面"Schema 设计"一节的原则扩一下；
分散或占比很低就接受丢弃，不用为了个别噪声硬改 schema。

### 已知限制：舍弃的内容不是 bug

`jichu` 里"中医学的哲学基础"（气一元论/阴阳/五行）、"经络"、"精气血津液神"这几章
零抽取比例很高（分别 100%/98%/94%），因为这些是纯哲学/概念性内容，schema 是围绕
疾病-证候-症状-方药设计的，本来就没有实体可抽。这是内容和 schema 范围不匹配，不是分段
或抽取的 bug；想覆盖这块内容需要新增实体/关系类型（如脏腑生理功能、经络循行、哲学概念），
是一次单独的 schema 设计决策，别顺手加。

## 抽取质量人工审阅（scripts/build_review_prompts.py）

不调用 LLM，只把「规则 + 原文 + 抽取结果」拼成一份可读的 markdown，交给人（或另一个模型）逐篇核对
有没有多抽/少抽/抽错。每篇文档一个独立 `## {doc_id}` 小节，内容整段包在一个 ``` 围栏里，
结尾固定接一句审阅指令；entities/triples 各一行一条（`json.dumps(..., ensure_ascii=False)`，不
pretty-print），方便逐行对照，不占篇幅。

```bash
.venv/bin/python scripts/build_review_prompts.py \
  --split neike_trial_v2_pro --n 41 \
  --prompt-template prompts/tcm_prompt_template_v2_pro.txt \
  --out docs/tcm_extraction_review_prompts_v2_pro.md
```

- `--split` 决定读哪个 `data/work/TCM/{split}/{docs,extraction_valid}.jsonl`；`--n` 控制取前几篇
  （默认 10，全量审阅传实际文档数）。
- `--prompt-template`：传了就直接摘取该 prompt 模板文件里「文本：\n{TEXT}」占位符之前的全部内容
  （含段落分类表、实体/关系定义、输出规则、few-shot 示例）作为规则区，与实际产出这批抽取结果的
  prompt 逐字一致——**换了 prompt 版本（如 v2/v2_pro）必须带这个参数**，否则会退回到用
  `schema/tcm_schema.yaml` 动态渲染的规则区，可能和实际用的 prompt 对不上。不传时才用于最初的
  base prompt（`prompts/tcm_prompt_template.txt`）审阅场景。
- 输出文件名按 split 区分（`tcm_extraction_review_prompts{_v2,_v2_pro,...}.md`），不要互相覆盖。

## 部署（czt666.cn/kg/）

```bash
./deploy.sh              # 构建前端 + 同步代码，重启服务（日常改代码/前端后用这个）
./deploy.sh --data       # 追加同步 data/work/（跑完新 pipeline 阶段 / 重新 merge 后才需要，~200MB+，较慢）
./deploy.sh --env        # 追加同步 .env（换了 API key 才需要）
```

`deploy.sh` 做的事：本地 `npm run build`（服务器只有 1 核/964MB，跑不动 `npm install`/`vite build`）
→ rsync 同步 `src/schema/prompts/config.yaml` → tar+ssh 同步 `web/dist/`（本机 openrsync 和服务器
GNU rsync 在大文件上有协议兼容 bug，踩过坑，别改回 rsync/scp）→ 按 flag 同步 `data/work/`/`.env`
→ `systemctl restart kg-pipeline.service` → 重试 curl 验证 `/kg/` 和 `/api/merged` 是否 200。

服务器目录（`root@39.106.77.104:/www/wwwroot/kg-pipeline/`）结构和本地仓库一致：
`src/ schema/ prompts/ config.yaml web/dist/ data/work/ .venv/(py3.9) .env`。serve.py 只读
`web/dist/`，不读 `web/src/`，所以前端改动不 build 不会生效。

进程：`kg-pipeline.service`（systemd，`ExecStart=.venv/bin/python src/serve.py --port 8787`，
`Restart=on-failure`）。nginx（`/www/server/panel/vhost/nginx/czt666.cn.conf`）把
`location ^~ /kg/` 和 `location ^~ /api/` 都反代到 `127.0.0.1:8787`（8787 只监听 loopback，
firewalld 没放行，外网连不到，必须走 nginx）。

调试用：

```bash
ssh root@39.106.77.104                                    # 服务器（本机 ~/.ssh/config 已配好别名）
ssh root@39.106.77.104 journalctl -u kg-pipeline.service -n 50 --no-pager   # 后端报错看这个
curl -s https://czt666.cn/api/merged | python3 -m json.tool   # 各数据集当前 splits/节点边数，最快的健康检查
```

- 前端页面：https://czt666.cn/kg/#/graph
- 该服务器同时挂了别的项目（BT 面板管理），只有 1 核/964MB，非常吃紧——排查变慢/502 先看
  `top`/`free -h`，大概率是别的进程（曾经是一个崩溃重启循环的废弃 Java 项目）在抢资源，不一定是
  kg-pipeline 自己的问题。

## Schema 设计

- `kind: intrinsic` 挂成头实体 `attributes` 里的字符串（字面量尾实体）；`relational` 才是图里的边。
- `domain`/`range` 是硬约束：类型不符会被丢弃（`type_violation`），头尾颠倒但类型对得上会自动
  翻转（`flipped`）。某关系被系统性丢弃较多时，先找用户确认要放宽约束还是接受丢弃，不要擅自改。
