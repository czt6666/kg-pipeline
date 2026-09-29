# KG Pipeline — 自动构建 + 检索知识图谱流水线

从文本抽取实体/关系三元组，构建知识图谱，并在 DocRED / GenWiki 上对齐 GraphRefine/GenRES
协议评测（G-BLEU / G-ROUGE / G-BERTScore / GenRES 五维），提供检索与可视化界面。

- 方案与创新点：`docs/SOLUTION.md`
- 技术设计：`docs/DESIGN.md`（v4）
- 评测结果与差距归因：`docs/ACCURACY.md`

## 1. 环境

```bash
uv venv .venv --python 3.11
uv pip install -r requirements.txt   # 若缺失，见 pyproject/uv.lock
cp .env.example .env                 # 填写 SHEEPWALL_API_KEY 等（.env 已在 .gitignore，勿提交）
```

关键依赖：`requests tiktoken pyyaml json-repair networkx numpy scikit-learn gensim faiss-cpu
bert-score rouge-score nltk`。

LLM 网关（SHEEPWALL）通过环境变量读取，**key 绝不写进代码/日志**：

```bash
export SHEEPWALL_API_KEY=...         # 或写进 .env
export SHEEPWALL_BASE_URL=https://test.sheepwall.com/fe-llm-gateway/
export SHEEPWALL_MODEL=deepseek-v4-pro
export SHEEPWALL_EMBEDDING_MODEL=azure/text-embedding-3-small
```

> `deepseek-v4-pro` 是推理模型，抽取调用走 `/v1/messages` 并 `"thinking":{"type":"disabled"}`
> 关闭思维链（否则推理会吃掉全部 8192 输出预算、JSON 为空）。见 `src/llm_client.py`。

## 2. 流水线（六阶段）

所有命令在仓库根目录执行，`{dataset}` ∈ `docred|genwiki`，`{split}` ∈ `eval200|test|dev`。

```bash
# 阶段0 准备（schema / docs / gold / few-shot / prompt）
.venv/bin/python src/build_docred_eval200.py           # DocRED eval200 评测集对齐 GenRES
.venv/bin/python src/build_genwiki.py --split test     # GenWiki schema+docs+gold+prompt

# 阶段1 抽取（唯一 LLM 调用点，带磁盘缓存与并发）
.venv/bin/python src/stage1_extract.py --dataset docred --split eval200 --workers 12

# 阶段2 校验+溯源  阶段3 对齐  阶段4 建图
.venv/bin/python src/stage2_validate.py --dataset docred --split eval200
.venv/bin/python src/stage3_align.py    --dataset docred --split eval200
.venv/bin/python src/stage4_build_graph.py --dataset docred --split eval200

# 阶段5 评测（BLEU/ROUGE/BERTScore + GenRES；--skip-genres/--skip-bertscore 可分跑）
.venv/bin/python src/stage5_eval.py --dataset docred --split eval200

# 阶段6 检索索引（FAISS）
.venv/bin/python src/stage6_index.py --dataset docred --split eval200
```

阶段 2–6 均可在不触发 LLM 的情况下从上游文件重跑。

## 3. 检索与可视化

前端改动后需要先构建（生成物在 web/dist/，serve.py 只读这个目录）：

```bash
cd web && npm install && npm run build && cd ..
.venv/bin/python src/serve.py --port 8787
# 浏览器打开 http://localhost:8787
```

前端开发（热重载，API 请求会自动代理到 8787）：

```bash
cd web && npm run dev
# 浏览器打开 http://localhost:5173，同时保持 src/serve.py 在 8787 运行
```

部署到生产服务器（czt666.cn/kg/，nginx 反代到 127.0.0.1:8787，kg-pipeline.service 管理进程）：

```bash
./deploy.sh              # 同步代码 + 前端构建产物，重启服务
./deploy.sh --data       # 追加同步 data/work/（跑完新的 pipeline 阶段后才需要，较慢）
./deploy.sh --env        # 追加同步 .env（换了 API key 才需要）
```

三个面板：原文视图（mentions 坐标高亮、点击反查实体）· 图谱视图（vis-network 节点/边，
点击节点看属性）· 检索面板（语义检索 + 词法匹配 + 图搜索 BFS 三路并排）。

命令行检索：

```bash
.venv/bin/python src/retrieval.py --dataset docred --split eval200 --query "Who founded Harvard?"
```

## 4. 目录

```
schema/{dataset}_schema.yaml        固定 schema（实体类型 + 关系 kind/domain/range）
prompts/{dataset}_prompt_template.txt, {dataset}_fewshot.json
src/                                各阶段脚本 + 检索 + 后端
web/                                可视化前端（Vite + React，组件化，见 web/src/）
data/raw/{dataset}/                 原始数据（只读）
data/work/{dataset}/{split}/        中间文件 + eval/metrics.json
scripts/analyze_gap.py              差距归因分析
docs/SOLUTION.md, DESIGN.md, ACCURACY.md
```
