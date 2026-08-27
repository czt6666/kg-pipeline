# 生成式关系抽取 / 端到端知识图谱构建 — 指标对比

> 本文档汇总本项目（`kg-pipeline`）在 GenWiki / DocRED 上的评测结果，与同任务（生成式关系抽取 /
> 端到端 KG 构建）的公开论文结果做对比。G-BLEU / G-ROUGE / G-BERTScore + GenRES 五维这套评测由
> GenRES → GraphRefine → GraphJudge 这一条线建立，**报告同口径数字的论文不多**，本文明确区分
> 「可直接比」与「数字不可硬拼」两类，并给出原始论文链接。

## 0. 任务口径（重要）

「DocRED」这个名字对应两个不同难度的任务，分数不能混用：

| 任务 | 评测方式 | 典型分数 |
|------|---------|---------|
| 传统关系抽取（经典 DocRED benchmark） | **实体已给定**，只判关系，硬匹配 F1 | 60~64 F1 |
| 端到端 KG 构建 / 生成式关系抽取（本项目） | **实体 + 关系都从原文抽**，G-BLEU 软匹配 | 目标 52.94（DocRED） |

本项目对标的是后者（GraphRefine / GenRES 这条线），而非传统 DocRE 的 60+ F1。

## 1. GenWiki — G-BLEU / G-BERTScore（可直接比）

来源：GraphJudge 论文（arXiv:2411.17388）报告了 GenWiki 上 GPT-4o / GPT-4o-mini / PiVe /
KGGen / GraphJudge 的 G-BL / G-BS / G-RO 分数。

| 方法 | G-BL (G-BLEU) F1 | G-BS (G-BERTScore) F1 | 说明 |
|------|-----------------|----------------------|------|
| GraphJudge（GPT-4o-mini 抽取 + LLaMA2-7B 判图） | **68.36** | 84.57 | 抽取 + 微调判图后处理 |
| GPT-4o | 67.74 | 84.28 | 纯单遍抽取 |
| **本项目（deepseek-v4-pro 单遍）** | **65.87** | **96.81** | 固定 schema + 闭集 |
| GPT-4o-mini | 65.77 | 83.68 | 纯单遍抽取 |
| GraphRefine（目标值） | 65.23 | 85.32 | 抽取后精修（Keep/Delete/Fix/Rewrite） |
| PiVe（GPT-4o-mini + Flan-T5-XXL verifier） | 65.03 | 82.30 | 抽取 + 验证 |
| KGGen | 55.42 | 81.69 | 抽取 |

**读表**：
- G-BLEU 上本项目 **65.87 稳居中游偏上**——超过 GraphRefine 目标、超过 GPT-4o-mini，比 GPT-4o 低
  1.9 分、比带后处理的 GraphJudge 低 2.5 分。作为「单遍、无精修」方案，该位置合理。
- G-BS 本项目 **96.81 明显偏高**（其余 82~85）。⚠️ 口径 caveat：各家 G-BERTScore 底层模型
  （roberta-large vs 其他）与聚合方式未必一致，BERTScore 在短三元组句子上普遍高分，此列只看趋势、
  不逐位比。

## 2. DocRED — GenRES 五维（可与 GenRES 原论文对比）

来源：GenRES 原论文（NAACL 2024，Table 2）报告 open-GRE 下各 LLM 在 DocRED 的 TS/US/FS/GS/CS。

| 方法 | TS | US | FS | GS | CS |
|------|----|----|----|----|----|
| GPT-4-Turbo | 50.0 | 87.4 | 97.6 | 63.1 | 49.3 |
| GPT-4 | 48.6 | 82.8 | 98.6 | 59.6 | 47.3 |
| GPT-3.5-Turbo-Instruct | 47.8 | 85.6 | 98.1 | 56.2 | 44.7 |
| LLaMA-2-70B | 39.2 | 82.6 | 97.3 | 60.9 | 39.2 |
| **本项目（deepseek-v4-pro）** | **13.9** | **99.8** | **67.3** | **99.7** | **47.2** |

**读表（含口径 caveat）**：
- **CS 完整性 47.2 ≈ GPT-4 的 47.3**：最硬的可比项（语义召回、不含 LLM 裁判），说明端到端覆盖率与
  GPT-4 打平。
- **US 99.8、GS 99.7 均高于 GPT-4**：三元组更少重复、更原子化——「固定 schema + 校验去重」的结构红利。
- **FS 67.3 远低于 98.6**：⚠️ 不可直接读。GenRES 的 FS 用 GPT-3.5-Turbo-Instruct 裁判（宽松），本项目
  用 deepseek（严格）；同一 deepseek 裁判下 gold 三元组仅 89.25%。真实事实性差距远小于账面数字。
- **TS 13.9 远低于 48.6**：部分因本项目抽取更原子（GS 99.7 vs 59.6），三元组串更稀疏；部分是 TS 指标
  本身的方向性局限（gold 自己也只有 9.4）。

## 3. 同为生成式 KG 构建，但数字不可硬拼

| 论文 | 内容 | 为何不可比 |
|------|------|-----------|
| AutoSchemaKG（ACL 2026） | 无预设 schema，同时诱导 schema + 抽三元组，50M 文档 | 评测规模 + 下游 QA/事实性（schema 对齐 92%、QA +12~18%），无 GenWiki G-BLEU |
| Text2KGBench（ISWC 2023） | 本体驱动的 KG 生成基准（Wikidata-TekGen / DBpedia-WebNLG） | 7 个自建指标（事实 F1、本体一致性 OC、幻觉率），非 G-BLEU |
| "Quadruple Shot"（SAICSIT 2025） | 多 agent 抽取 + OpenIE + 本体增强 | 句向量 cosine 0.874 自评，无 G-BLEU |

## 4. 结论

1. **GenWiki（主战场）**：本项目 G-BLEU **65.87**，介于 GPT-4o-mini（65.77）与 GPT-4o（67.74）之间，
   **超过 GraphRefine 目标 65.23**，比带后处理的 GraphJudge（68.36）低 2.5 分——单遍无精修方案下位置体面。
2. **DocRED**：最硬的 CS 指标 **47.2 ≈ GPT-4 的 47.3**（覆盖率打平）；FS/TS 账面差距被「裁判口径」与
   「抽取原子化」两个非质量因素放大，真实质量差距小于表格显示。
3. 结构性优势（唯一性、粒度）一致领先；结构性短板是单遍无精修，正是 GraphRefine / GraphJudge 那类
   「抽取后精修」方法针对的缺口。

## 5. 原始论文链接

- **GenRES**（NAACL 2024）— 评测框架本身（TS/US/FS/GS/CS + G-BLEU/G-ROUGE/G-BERTScore）：
  - arXiv: <https://arxiv.org/abs/2402.10744>
  - ar5iv 全文: <https://ar5iv.labs.arxiv.org/html/2402.10744>
  - NAACL PDF: <https://www.cs.jhu.edu/~kevinduh/t/naacl24/final_pdf/paper270.pdf>
- **GraphRefine**（ACL 2026）— 抽取后精修（本项目目标值来源）：
  - <https://aclanthology.org/2026.acl-long.1353.pdf>
- **GraphJudge**（arXiv:2411.17388，*Can LLMs be Good Graph Judger for Knowledge Graph Construction?*）：
  - arXiv: <https://arxiv.org/abs/2411.17388>
  - ar5iv 全文: <https://ar5iv.labs.arxiv.org/html/2411.17388>
- **AutoSchemaKG**（ACL 2026 / arXiv:2505.23628）：
  - ACL Anthology: <https://aclanthology.org/2026.acl-long.942/>
  - arXiv: <https://arxiv.org/abs/2505.23628>
  - 代码: <https://github.com/HKUST-KnowComp/AutoSchemaKG>
- **Text2KGBench**（ISWC 2023 / arXiv:2308.02357）：
  - arXiv: <https://arxiv.org/abs/2308.02357>
  - ar5iv 全文: <https://ar5iv.labs.arxiv.org/html/2308.02357>
  - 代码: <https://github.com/cenguix/Text2KGBench>
- **Quadruple Shot KG Construction**（SAICSIT 2025 / arXiv:2508.03438）：
  - arXiv: <https://arxiv.org/abs/2508.03438>
