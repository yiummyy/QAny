# QAny Evaluation Toolkit

企业级知识库问答系统 **检索 / 性能 / 模型质量** 三维外部评估工具。

---

## 架构

```
eval/
├── __init__.py          # 包标记
├── __main__.py          # python -m eval 入口
├── cli.py               # 统一 CLI（子命令：retrieval / performance / quality / all）
├── dataset.py           # 标注数据集 v2 加载与校验 (EvalItemV2)
├── retrieval.py         # 检索质量评估 — MRR@K / NDCG@K / MAP@K / Recall@K
├── performance.py       # 系统性能评估 — QPS / TTFT / 延迟分位数
├── quality.py           # 模型质量评估 — Token F1 / Exact Match / ROUGE-L / Factual Accuracy
├── reporter.py          # 报告生成 — JSON + Markdown
├── data/
│   └── eval_set_v2.json # 扩展标注数据集（50 条，含 relevance_judgments + ground_truth_answer）
└── README.md
```

```
                    ┌──────────────┐
                    │   eval CLI   │
                    └──────┬───────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │  retrieval   │ │ performance  │ │   quality    │
    │  MRR@10      │ │  QPS         │ │  Token F1    │
    │  NDCG@10     │ │  TTFT        │ │  Exact Match │
    │  MAP@5       │ │  P50/P99     │ │  ROUGE-L     │
    │  Recall@K    │ │              │ │  Factual Acc │
    └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
           │                │                │
           ▼                ▼                ▼
    ┌──────────────────────────────────────────────────┐
    │              eval_set_v2.json                     │
    │  query + relevance_judgments + ground_truth_answer │
    └──────────────────────────────────────────────────┘
```

---

## 快速开始

### 安装依赖

```bash
cd eval/
pip install httpx  # 性能/质量评估需要
# jieba（可选，用于中文分词，提高 F1 精度）
pip install jieba
```

### 1. 检索质量评估

对比 raw（rerank 前 Top-20）与 rerank（精排后 Top-5）的排序质量。

```bash
# Direct 模式（默认）— 直接导入 backend 模块，无需启动服务
python -m eval retrieval --eval-set eval/data/eval_set_v2.json

# API 模式 — 后端需先启动
python -m eval retrieval --mode api --base-url http://localhost:8000
```

输出示例：
```
  MRR  raw@10=0.6520  rerank@5=0.7810
  NDCG raw@10=0.5830  rerank@5=0.7120
  MAP  raw@10=0.4210  rerank@5=0.5980
```

### 2. 系统性能压测

多并发 SSE 流式压测，精确测量 TTFT（逐 chunk 解析）。

```bash
python -m eval performance \
    --eval-set eval/data/eval_set_v2.json \
    --base-url http://localhost:8000 \
    --concurrency 1,5,10,20
```

### 3. 模型生成质量评估

对 LLM 生成答案做多维度评分（需要 `ground_truth_answer` 字段）。

```bash
python -m eval quality \
    --eval-set eval/data/eval_set_v2.json \
    --base-url http://localhost:8000
```

### 4. 一键全量

```bash
python -m eval all \
    --eval-set eval/data/eval_set_v2.json \
    --base-url http://localhost:8000 \
    --output-dir reports
```

---

## 指标说明

### 检索质量

| 指标 | 公式 | 含义 |
|---|---|---|
| **MRR@K** | mean(1/rank_first_relevant) | 第一个相关文档平均排位的倒数 |
| **NDCG@K** | DCG/IDCG | 归一化折损累积增益，考虑排序位置和相关性等级 |
| **MAP@K** | mean(Σ Precision@i / total_relevant) | 每个相关位置的精确率取均值 |
| **Recall@K** | relevant_hits_at_k / total_relevant | Top-K 中命中相关文档的比例 |

### 系统性能

| 指标 | 含义 |
|---|---|
| **QPS** | 每秒处理请求数（并发/总耗时） |
| **TTFT** | Time To First Token — 首个 MESSAGE chunk 到达时间 |
| **Total P50/P99** | 端到端响应时间的百分位数 |

### 模型质量

| 指标 | 含义 |
|---|---|
| **Token F1** | 分词后的 Precision/Recall 调和均值 |
| **Exact Match** | 标准化后是否完全一致 |
| **ROUGE-L** | 最长公共子序列 F1 |
| **Factual Accuracy** | must_contain 全命中 且 must_not_contain 零违规 |

---

## 数据集标注指南

`eval_set_v2.json` 相比 v1 新增三个字段：

```json
{
  "relevance_judgments": {
    "chunk_handbook_001": 3,
    "chunk_handbook_005": 1
  },
  "ground_truth_answer": "年假制度：工龄1-10年5天...",
  "must_contain": ["年假", "天数"],
  "must_not_contain": ["病假"]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `relevance_judgments` | 检索评估必填 | chunk_id/doc_id → 0-3 相关性，3=高度相关 |
| `ground_truth_answer` | 质量评估必填 | 人工标注的标准答案 |
| `must_contain` | 推荐 | 答案必须包含的关键事实 |
| `must_not_contain` | 推荐 | 答案禁止包含的内容 |

---

## 后端评估端点

评估工具在 `api` 模式下需要后端提供 `/api/v1/eval/retrieval` 端点（已在 `backend/app/api/v1/eval.py` 中实现并注册）。

该端点返回 raw Top-20 和 rerank Top-5 的完整排序列表，绕过 Agent Loop，专供评估使用。
