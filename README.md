# KG Pipeline

一个面向知识抽取、图谱构建、检索与可视化的项目骨架，当前按 **Pipeline / Graph / Services / Web** 四层拆分。

## 目录结构

```text
apps/                          服务启动入口
  backend_server.py            后端服务：静态页面 + pipeline 侧 API
  kg_server.py                 图谱服务：图谱 / 检索 / Agent API

core/                          配置、路径、I/O、LLM 基础能力
prompting/                     PromptBuilder + PromptStore
assistant/                     TCM Agent Loop
graph/
  merge/                       多轮抽取合并
  retrieval/                   图谱检索
services/                      backend / kg server 实现

resources/
  prompts/                     统一提示词目录（按域 / 数据集 / 版本管理）
  schemas/                     统一 schema 目录

src/                           pipeline 阶段入口脚本
preprocess/                    预处理入口脚本
scripts/                       研究 / 运维 / 实验脚本
web/                           前端（纯前端项目）

data/
  raw/                         原始输入数据
  pipeline/<dataset>/splits/   pipeline 运行数据
  graph/<dataset>/<graph>/     发布后的知识图谱数据

tests/
```

## Prompt 管理

所有可配置提示词统一放在 `resources/prompts/`：

```text
resources/prompts/
  docred/v1/
  genwiki/v1/
  tcm/v1|v2|v2_pro|v4|v4_pro/
  simplify/v1/
  genres/v1/
  retrieval_summary/v1/
  registry.yaml                当前默认版本注册表
```

运行时统一通过 `prompting.PromptStore` 读取；抽取阶段会把本次使用的 prompt 版本写入 `prompt_lock.json`。

## 数据布局

- Pipeline 中间产物：`data/pipeline/<dataset>/splits/<split>/`
- 多轮实验：`data/pipeline/<dataset>/splits/experiments/<experiment>/rounds/<round>/`
- 图谱产物：`data/graph/<dataset>/<graph>/`

这样可以做到：
- pipeline 数据和最终图谱数据分离
- 多轮 round 归档到同一个 experiment 下面
- 后端服务只关心 pipeline 数据，图谱服务只关心 graph 数据

## 常用命令

### 1) 生成 / 运行 pipeline

```bash
.venv/bin/python src/build_docred_eval200.py
.venv/bin/python src/build_genwiki.py --split test --version v1
.venv/bin/python src/stage1_extract.py --dataset docred --split eval200
.venv/bin/python src/stage2_validate.py --dataset docred --split eval200
.venv/bin/python src/stage3_align.py --dataset docred --split eval200
.venv/bin/python src/stage4_build_graph.py --dataset docred --split eval200
.venv/bin/python src/stage5_eval.py --dataset docred --split eval200
.venv/bin/python src/stage6_index.py --dataset docred --split eval200
.venv/bin/python src/stage7_merge.py --dataset docred --splits eval200 --out merged
```

### 2) 多轮抽取实验

```bash
.venv/bin/python scripts/extract_multiround.py \
  --dataset TCM \
  --split neike_trial \
  --experiment neike_trial_v4_pro_3round \
  --rounds 3 \
  --temperature 0.5
```

### 3) 启动服务

问答 Agent 使用 OpenAI `gpt-4.1`。启动图谱服务前，在仓库根目录的 `.env` 中设置
`OPENAI_API_KEY`；问答中的向量检索使用 OpenAI `text-embedding-3-small`。

```bash
# 后端服务：页面 + pipeline API
.venv/bin/python apps/backend_server.py --port 53785

# 图谱服务：图谱 / 检索 / Agent API
.venv/bin/python apps/kg_server.py --port 53786

# 前端开发
cd web && npm run dev
```

Vite 开发代理：
- `/api/*` -> backend server
- `/api/kg/*` -> kg server

## 设计原则

- Stage 主逻辑不做算法性改写，只做职责拆分与目录重组。
- Prompt、Schema、Data Path 全部收敛到统一注册与路径约定。
- 前端、后端、图谱服务解耦，可独立部署。
- 内部代码目录尽量一层语义化命名，避免仓库名和包名重复套娃。
