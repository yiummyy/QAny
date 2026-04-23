# 企业知识库问答系统 MVP 设计稿

- **Spec ID**: 2026-04-23-enterprise-knowledge-qa-mvp-design
- **日期**: 2026-04-23
- **作者**: Meta Claude Code（MVP 模式 Design First）
- **依据文档**: `企业级知识库问答系统PRD.md`、`Harness Engineering.md`、`RAG参考.md`
- **状态**: 待用户批准

---

## 0. 概览

### 0.1 交付目标

本 Spec 描述企业级知识库问答系统 **MVP 核心切片** 的完整技术设计。MVP 范围锁定为：**KnowledgeQA 单 Agent 走通端到端 RAG 问答链路**，严格遵循 Harness Engineering 规范的骨架优先策略，为未来扩展至 4 个 Agent（KnowledgeQA/ServiceTicket/SalesContent/OpsSupport）打好地基。

### 0.2 关键决策一览

| 维度 | 决策 |
|------|------|
| 交付粒度 | MVP 核心切片：KnowledgeQA Agent + RAG 端到端闭环 |
| Harness 落地深度 | 骨架优先（主循环 + 工具路由表 + 磁盘持久化） |
| 后端技术栈 | Python 3.11 + FastAPI + 自建 Harness（不引入 LangChain/LlamaIndex） |
| 前端技术栈 | Vite + React 18 + TypeScript + TailwindCSS + Zustand（流式）+ TanStack Query（CRUD） |
| 大模型接入 | 云端 API 起步（DashScope Qwen-Plus / DeepSeek），Provider 抽象预留本地 vLLM 扩展 |
| Embedding/Rerank | 本地 BGE-M3 + BGE-Reranker-v2-m3，内嵌 backend 进程 |
| 知识源 | 仅本地文档上传（PDF/Word/Markdown/TXT），DocumentSource 抽象 |
| 检索存储 | Elasticsearch 8.11 + IK 分词器（三合一：BM25 + dense_vector + filter） |
| 关系型存储 | PostgreSQL 16（用户/文档元信息/问答日志/反馈/运行时配置） |
| 缓存 | Redis 7（session 短期上下文/计数/限流/分布式锁） |
| 磁盘 SSOT | `backend/data/{sessions,tasks,uploads}` |
| 权限模型 | 基础 RBAC：3 角色 × 3 级别（guest/employee/admin × L1/L2/L3），ABAC 字段预留不启用 |
| Rerank 默认 | 开启，admin 后台可切换 |
| Chunk 参数 | 512 token / chunk，overlap 128 |
| 部署形态 | docker-compose 一键起（PostgreSQL + ES + Redis + backend + frontend） |
| 监控 | Prometheus + Grafana 作为可选 profile |
| DoD 准确率门槛 | 85%（MVP 阶段黄金集 50 组冒烟） |

---

## 1. 系统架构

### 1.1 分层架构

```
┌─────────────────────────────────────────────────────┐
│  Frontend (Vite + React + TypeScript)               │
│  对话主页 / 登录 / 历史 / Admin（知识/设置/日志）    │
└─────────────────────────────────────────────────────┘
                      │ REST + SSE
┌─────────────────────────────────────────────────────┐
│  FastAPI Gateway                                     │
│  /api/v1/qa/ask (SSE)  /api/v1/knowledge/*          │
│  /api/v1/auth/*        /api/v1/feedback             │
│  /api/v1/admin/*       /healthz  /metrics           │
└─────────────────────────────────────────────────────┘
                      │
┌─────────────────────────────────────────────────────┐
│  Harness Core （The Loop is Sacred）                 │
│  ├─ agent_loop.py     极简 while True 主循环        │
│  ├─ tool_registry.py  TOOL_HANDLERS 字典路由        │
│  ├─ context.py        上下文装配 / 三层压缩         │
│  ├─ session_store.py  JSONL 信箱 + 磁盘持久化        │
│  ├─ degrade.py        降级判定中心                  │
│  └─ fsm.py            FSM 状态机（MVP 预留空壳）    │
└─────────────────────────────────────────────────────┘
                      │
┌───────────────────┬──────────┬──────────────────────┐
│  Tools Layer      │ Providers│  Knowledge Pipeline  │
│  • rewrite_query  │ ├─Qwen   │  • Parsers           │
│  • hybrid_search  │ ├─DeepSk │  • Chunker           │
│  • rerank         │ └─vLLM¹  │  • Embedder (BGE-M3) │
│  • permission_ck  │          │  • Indexer           │
│  • generate       │ ¹空壳保留│                      │
│  • hallucination  │          │                      │
└───────────────────┴──────────┴──────────────────────┘
                      │
┌─────────────────────────────────────────────────────┐
│  Storage                                             │
│  • PostgreSQL 16: users/documents/qa_logs/feedbacks │
│  • Elasticsearch 8.11: qa_chunks（检索唯一索引）     │
│  • Redis 7: session:{id} / tokens / ratelimit       │
│  • Disk: data/sessions/YYYY-MM-DD/*.jsonl           │
│          data/tasks/task_*.json                     │
│          data/uploads/*                             │
└─────────────────────────────────────────────────────┘
```

### 1.2 架构风格：Agent-as-Orchestrator

MVP 选择 **方案 A：Agent-as-Orchestrator**。所有 RAG 步骤（改写/检索/Rerank/权限/生成/幻觉检测）抽象为独立工具，通过极简 `while True` 主循环 + `TOOL_HANDLERS` 字典调度。首 token 延迟通过 Prompt 强约束（首轮强制调 `rewrite_query + hybrid_search`）压缩。

扩展收益：后续接入 ServiceTicket/SalesContent/OpsSupport 三个 Agent 时，只需新增工具和场景化 Prompt，Harness 骨架零改动。

### 1.3 仓库目录结构

```
qa-system/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 入口
│   │   ├── config.py                # pydantic-settings
│   │   ├── logging_conf.py          # structlog
│   │   ├── api/
│   │   │   ├── qa.py                # /qa/ask SSE
│   │   │   ├── knowledge.py         # 上传/同步/查询/删除
│   │   │   ├── auth.py              # 登录/JWT/刷新/登出
│   │   │   ├── feedback.py          # 点赞/点踩
│   │   │   ├── admin.py             # settings/logs/metrics
│   │   │   └── deps.py              # 鉴权依赖链
│   │   ├── harness/                 # ★ Harness 核心
│   │   │   ├── agent_loop.py
│   │   │   ├── tool_registry.py
│   │   │   ├── context.py
│   │   │   ├── session_store.py
│   │   │   ├── degrade.py
│   │   │   ├── fsm.py               # 空壳占位
│   │   │   └── models.py            # pydantic 契约
│   │   ├── tools/                   # ★ TOOL_HANDLERS 实体
│   │   │   ├── rewrite_query.py
│   │   │   ├── hybrid_search.py
│   │   │   ├── rerank.py
│   │   │   ├── permission_check.py
│   │   │   ├── generate_answer.py
│   │   │   └── hallucination_check.py
│   │   ├── providers/               # LLM Provider 抽象
│   │   │   ├── base.py              # BaseLLMProvider 接口
│   │   │   ├── dashscope_provider.py
│   │   │   ├── deepseek_provider.py
│   │   │   └── vllm_provider.py     # 空壳占位
│   │   ├── knowledge/
│   │   │   ├── sources/
│   │   │   │   ├── base.py          # DocumentSource ABC
│   │   │   │   └── local_upload.py
│   │   │   ├── parsers/             # pdf.py / docx.py / md.py / txt.py
│   │   │   ├── chunker.py
│   │   │   ├── embedder.py          # BGE-M3
│   │   │   ├── reranker.py          # BGE-Reranker-v2-m3
│   │   │   └── indexer.py
│   │   ├── rbac/
│   │   │   ├── roles.py
│   │   │   └── filter_builder.py
│   │   ├── storage/
│   │   │   ├── pg.py                # SQLAlchemy async + asyncpg
│   │   │   ├── es_client.py
│   │   │   └── redis_client.py
│   │   ├── models/                  # SQLAlchemy ORM 模型
│   │   │   ├── user.py
│   │   │   ├── document.py
│   │   │   ├── qa_log.py
│   │   │   ├── feedback.py
│   │   │   └── settings.py
│   │   ├── prompts/                 # Prompt 模板
│   │   │   ├── rewrite_query.md
│   │   │   ├── generate_answer.md
│   │   │   └── hallucination_check.md
│   │   └── migrations/              # Alembic
│   ├── tests/
│   │   ├── unit/
│   │   ├── contract/
│   │   ├── integration/
│   │   ├── eval/                    # 黄金集评测 runner
│   │   └── fixtures/
│   ├── scripts/
│   │   ├── init_es.py
│   │   ├── seed_users.py
│   │   ├── seed_docs.py
│   │   └── reindex.py
│   ├── data/                        # Docker volume 挂载
│   │   ├── sessions/YYYY-MM-DD/*.jsonl
│   │   ├── tasks/*.json
│   │   ├── uploads/*
│   │   └── backups/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── routes/
│   │   ├── components/
│   │   │   ├── ChatBubble.tsx
│   │   │   ├── SourceList.tsx
│   │   │   ├── ConfidenceBadge.tsx
│   │   │   └── InputBox.tsx
│   │   ├── hooks/useSSE.ts
│   │   └── store/chatStore.ts       # Zustand
│   ├── index.html
│   ├── vite.config.ts
│   └── Dockerfile
├── docker-compose.yml
├── deploy.sh
├── .env.example
├── docs/superpowers/specs/          # 本文件所在
└── README.md
```

---

## 2. Harness 核心骨架

### 2.1 极简主循环（The Loop is Sacred）

主循环硬约束：`MAX_STEPS = 10`，防跑飞；主循环不感知具体工具名；所有扩展靠注册新工具。

伪代码（真实实现带 pydantic 校验与异常处理）：

```python
# backend/app/harness/agent_loop.py
MAX_STEPS = 10
COMPACT_THRESHOLD = 3000  # tokens

async def run(
    query: str,
    session_id: str,
    user_claims: UserClaims,
) -> AsyncIterator[Event]:
    ctx = await context.build(session_id, query, user_claims)
    session_store.append(session_id, {"role": "user", "content": query})

    for step in range(MAX_STEPS):
        decision = await llm.plan(ctx)   # 返回 tool_call 或 final_answer

        if decision.type == "final_answer":
            async for chunk in llm.stream_final(ctx):
                yield Event("message", chunk)
                session_store.append_stream_chunk(session_id, chunk)
            yield Event("done", decision.metadata)
            session_store.append(session_id, {"role": "assistant", ...})
            return

        handler = TOOL_HANDLERS.get(decision.tool)
        if not handler:
            yield Event("error", f"unknown tool: {decision.tool}")
            return

        result = await handler(**decision.args, user_claims=user_claims)
        ctx.append_tool_result(decision.tool, result)
        session_store.append(session_id, {
            "role": "tool", "name": decision.tool, "summary": result.summary
        })

        if ctx.token_count() > COMPACT_THRESHOLD:
            ctx = await context.compact(ctx)

    yield Event("error", "max steps exceeded")
```

### 2.2 工具路由表（TOOL_HANDLERS）

```python
# backend/app/harness/tool_registry.py
TOOL_HANDLERS: dict[str, ToolHandler] = {}

def register(name: str, schema: type[BaseModel]):
    def deco(fn):
        TOOL_HANDLERS[name] = ToolHandler(name=name, schema=schema, fn=fn)
        return fn
    return deco
```

工具契约：

- 输入用 pydantic schema，供 LLM `function_call` 参数校验
- 所有工具接收 `user_claims` 作为隐式参数（由主循环注入），**永远不信任 LLM 生成的权限字段**
- 返回 `ToolResult(status, data, summary)`
  - `summary`：短文本，给 LLM 看，用于上下文压缩
  - `data`：完整数据，供主循环/下游工具消费，不直接进 LLM 上下文

### 2.3 工具清单（MVP 阶段 6 个）

| 工具名 | 输入 | 输出 | 对应 PRD |
|--------|------|------|----------|
| `rewrite_query` | query, history | rewritten_query, intent, entities | §6.1.4 指代消解 + §4.1.2 意图/槽位 |
| `hybrid_search` | query, top_k, filters | chunks[] + scores | §7.3.4 混合检索 |
| `rerank` | query, chunks | top_n chunks | §7.3.4 BGE-Reranker |
| `permission_check` | user_claims, chunk_metadata | bool | §4.1.3 工具 4 |
| `generate_answer` | query, chunks, user_claims | 流式 text + sources + confidence | §4.1.3 工具 3 |
| `hallucination_check` | answer, chunks | score, verdict | §7.3.6 幻觉检测 |

### 2.4 磁盘 SSOT

**Session JSONL**（`backend/data/sessions/YYYY-MM-DD/{session_id}.jsonl`，Append-only）：

```jsonl
{"ts":"2026-04-22T14:30:01Z","type":"user","content":"年假制度是什么？"}
{"ts":"2026-04-22T14:30:02Z","type":"tool_call","name":"rewrite_query","args":{...}}
{"ts":"2026-04-22T14:30:02Z","type":"tool_result","name":"rewrite_query","summary":"意图=制度查询","data_ref":"data/tasks/task_abc.json"}
{"ts":"2026-04-22T14:30:04Z","type":"tool_call","name":"hybrid_search","args":{...}}
{"ts":"2026-04-22T14:30:05Z","type":"tool_result","name":"hybrid_search","summary":"召回 18 条","data_ref":"data/tasks/task_def.json"}
{"ts":"2026-04-22T14:30:07Z","type":"assistant_stream","chunk":"根据《员工手册"}
{"ts":"2026-04-22T14:30:09Z","type":"assistant_done","sources":[...],"confidence":0.92}
```

- JSONL 只写摘要，完整数据用 `data_ref` 指回 `data/tasks/*.json`，避免 session 膨胀
- 按天自然分区（`YYYY-MM-DD/` 目录），超过 30 天整天删除
- 同一天目录下可容纳多个 session 文件

**Task JSON**（`backend/data/tasks/task_{uuid}.json`，单次工具调用完整产物）：

```json
{
  "task_id": "task_abc123",
  "session_id": "session_xyz",
  "tool": "hybrid_search",
  "status": "completed",
  "created_at": "2026-04-22T14:30:02Z",
  "completed_at": "2026-04-22T14:30:04Z",
  "args": {},
  "result": {},
  "depends_on": ["task_000"],
  "spawned_by": "session_xyz#step_1"
}
```

MVP 的任务 DAG 退化为单次调用链（无并发子任务），`depends_on` 字段预留给后续多 Agent 协作。

### 2.5 三层上下文压缩策略

对齐 PRD §6.1.4 Token 预算 + Harness 准则 2：

| 层级 | 触发条件 | 动作 | MVP |
|------|----------|------|-----|
| 微压缩 | 每轮工具调用后 | 旧工具 `data` 字段丢弃，保留 `summary` | ✅ 必做 |
| 自动压缩 | `ctx.token_count() > 3000` | 调 LLM 提炼历史为 200 token 摘要，回填 system message | ✅ 必做 |
| 手动压缩 | 用户 `/reset` | 清空 session，保留用户画像 | ⚪ P2 |

所有压缩动作写入 JSONL（`type: "compaction"`）便于审计。

---

## 3. RAG 管线

### 3.1 离线知识处理管线

触发入口：`POST /api/v1/knowledge/upload`（单文件）/ `POST /api/v1/knowledge/sync`（批量重解析）。

```
[原始文件 backend/data/uploads/]
       │
       ▼
┌──────────────────────────────────┐
│  1. Parser                       │
│     ├─ PDF  → pypdf              │
│     ├─ DOCX → python-docx        │
│     ├─ MD   → markdown-it-py     │
│     └─ TXT  → 直读                │
│  输出: [{text, section}]         │
└──────────────────────────────────┘
       ▼
┌──────────────────────────────────┐
│  2. Chunker                      │
│  - 512 token/chunk，overlap 128  │
│  - 段落边界优先，不切断句        │
│  - 保留 section 路径             │
└──────────────────────────────────┘
       ▼
┌──────────────────────────────────┐
│  3. Embedder (BGE-M3, 1024 dim)  │
│  - batch_size=32                 │
│  - L2 归一化（供 cosine 相似度） │
└──────────────────────────────────┘
       ▼
┌──────────────────────────────────┐
│  4. Indexer → ES                 │
│  - bulk insert，幂等（chunk_id=md5）│
│  - 同 doc 旧 chunk 先 delete 再写  │
│  - 同步更新 PG documents.chunk_count│
└──────────────────────────────────┘
```

幂等规则：

- `chunk_id = md5(doc_id + chunk_index + content_hash)`
- 文档更新时按 `doc_id` 批量删除旧 chunk 再写新 chunk，避免残留
- PG documents 记录 `file_hash`（sha256 整文件），重复上传直接返回已有 doc_id

### 3.2 Elasticsearch 索引（唯一索引 qa_chunks）

```json
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "ik_smart_plus": {"type": "custom", "tokenizer": "ik_smart"}
      }
    }
  },
  "mappings": {
    "properties": {
      "chunk_id":         {"type": "keyword"},
      "doc_id":           {"type": "keyword"},
      "doc_name":         {"type": "keyword"},
      "chunk_index":      {"type": "integer"},
      "content":          {"type": "text", "analyzer": "ik_smart_plus"},
      "section":          {"type": "keyword"},
      "embedding":        {"type": "dense_vector", "dims": 1024, "similarity": "cosine", "index": true},
      "permission_level": {"type": "keyword"},
      "department":       {"type": "keyword"},
      "source_type":      {"type": "keyword"},
      "updated_at":       {"type": "date"},
      "content_hash":     {"type": "keyword"}
    }
  }
}
```

- 使用 IK 中文分词器，标准分词对中文按字切会让 BM25 失效
- 镜像采用 `infinilabs/elasticsearch-ik:8.11`
- 冗余字段 `doc_name` / `permission_level` 用于结果展示与权限前置过滤，一致性由 indexer 双写保证（先 PG 后 ES，失败重试 + `scripts/reindex.py` 兜底）

### 3.3 在线检索：混合查询 + RRF 融合

```python
async def hybrid_search(query: str, top_k: int, filters: dict, *, user_claims):
    es_filter = rbac.build_filter(user_claims) | filters
    bm25_task = es.search(
        index="qa_chunks",
        query={"bool": {"must": [{"match": {"content": query}}], "filter": es_filter}},
        size=top_k,
    )
    vec_task = es.search(
        index="qa_chunks",
        knn={
            "field": "embedding",
            "query_vector": await embedder.encode(query),
            "k": top_k,
            "num_candidates": top_k * 5,
            "filter": es_filter,
        },
        size=top_k,
    )
    bm25_hits, vec_hits = await asyncio.gather(bm25_task, vec_task)
    return rrf_fuse(bm25_hits, vec_hits, k=60)
```

RRF 融合：`score(doc) = Σ 1/(k + rank_i)`，k=60（Elastic 官方推荐）。

### 3.4 Rerank

- 模型：BGE-Reranker-v2-m3（本地 ONNX，CPU ~50ms/pair）
- 默认开启，`qa_settings.config.rerank_enabled` 可由 admin 后台切换
- 输入 Top-20 候选 → 输出 Top-5 精选
- 关闭时直接取 RRF Top-5

### 3.5 Prompt 设计

三个 Prompt 文件，独立维护，便于 A/B：

| 文件 | 作用 | 关键约束 |
|------|------|----------|
| `prompts/rewrite_query.md` | 改写 + 意图 + 槽位 | JSON 输出：`{rewritten, intent, entities}`；历史对话指代消解 |
| `prompts/generate_answer.md` | 最终答案生成 | 强制引用 `[S1]` 索引；无据可查强制回 "抱歉，我无法确定答案..." |
| `prompts/hallucination_check.md` | 置信度打分 | 逐句对齐源 chunk，输出 0-1 score + verdict |

防幻觉关键技巧（写入 `generate_answer.md`）：

1. 每段引用必须带 `[S1]` `[S2]` 索引，后处理替换为上标形式
2. 检索结果 `score < 0.4` 或无结果 → 强制返回模板
3. 禁止扩展补充知识库外知识（Prompt 明确声明"仅基于以下文档回答"）

### 3.6 幻觉检测降级阈值

| 置信度 | 区间 | 动作 |
|--------|------|------|
| high | ≥ 0.8 | 直通 |
| medium | [0.6, 0.8) | 前端展示"建议参考原文" |
| low | < 0.6 | 改写为兜底模板 + `confidence: "low"` |

阈值存 `qa_settings.config.hallucination_threshold`，默认 0.6。

---

## 4. API 契约与数据模型

### 4.1 存储分布总表

| 数据类别 | 存储 | 说明 |
|---------|------|------|
| 用户账户 / 角色 / 权限 | PostgreSQL | 事务 + 强一致，bcrypt 密码 |
| 文档元信息（权威源） | PostgreSQL | 关系完整 |
| 文档 chunks + embedding | ES `qa_chunks` | 三合一检索，冗余必要字段 |
| 问答日志 | PostgreSQL | JOIN 分析方便 |
| 用户反馈 | PostgreSQL | 与 qa_logs 关联 |
| 运行时配置 | PostgreSQL `qa_settings` | JSONB 灵活 |
| Session 短期上下文 | Redis | 30min TTL |
| Token / 限流计数 | Redis | 原子 INCR |
| Session JSONL + Task DAG + Uploads | Disk | Harness SSOT |

### 4.2 REST API 清单

| Method | Path | 鉴权 | 用途 |
|--------|------|------|------|
| POST | `/api/v1/auth/login` | 公开 | 登录，返回 JWT |
| POST | `/api/v1/auth/refresh` | JWT | 刷新 access token |
| POST | `/api/v1/auth/logout` | JWT | 登出，jti 入黑名单 |
| POST | **`/api/v1/qa/ask`** | JWT | **SSE 流式问答（核心）** |
| GET | `/api/v1/qa/sessions/{id}` | JWT | 查询单次会话日志（仅本人或 admin） |
| GET | `/api/v1/qa/chunks/{id}` | JWT | 按 chunk_id 取原文（Source 抽屉用） |
| POST | `/api/v1/knowledge/upload` | admin | 上传文档（multipart） |
| POST | `/api/v1/knowledge/sync` | admin | 批量重解析 |
| GET | `/api/v1/knowledge/documents` | admin | 文档列表分页 |
| DELETE | `/api/v1/knowledge/documents/{id}` | admin | 删除（级联删 chunks） |
| POST | `/api/v1/feedback` | JWT | 点赞/点踩 |
| GET | `/api/v1/admin/settings` | admin | 读 qa_settings |
| PUT | `/api/v1/admin/settings` | admin | 更新 qa_settings（乐观锁） |
| GET | `/api/v1/admin/logs` | admin | 问答日志分页 |
| GET | `/api/v1/admin/metrics` | admin | Token/成本/延迟聚合 |
| GET | `/healthz` | 公开 | 健康检查 |
| GET | `/metrics` | 公开（内网） | Prometheus exposition |

### 4.3 核心接口：`POST /api/v1/qa/ask`

**Request**：
```json
{
  "question": "公司年假制度是怎样的？",
  "session_id": "sess_xyz123",
  "input_type": "text",
  "scene": "general"
}
```

**SSE 响应帧序列**：

```
event: status
data: {"phase":"retrieving","message":"🔍 正在检索知识库..."}

event: status
data: {"phase":"thinking","message":"🤖 AI 正在思考..."}

event: message
data: {"chunk":"根据《员工手册"}

event: message
data: {"chunk":" V2.0》..."}

event: done
data: {
  "full_answer":"根据《员工手册 V2.0》...",
  "sources":[{"doc_name":"员工手册 V2.0","section":"第3章第2节","doc_id":"doc_001","chunk_id":"chk_042","score":0.92}],
  "confidence":"high",
  "confidence_score":0.92,
  "related_questions":["如何申请年假？","年假可以累积吗？"],
  "response_time_ms":3240,
  "tokens":{"input":1523,"output":186,"total":1709,"cost_rmb":0.024},
  "trace_id":"tr_abc123"
}

event: error
data: {"code":50001,"message":"大模型服务超时","fallback_answer":"系统繁忙..."}
```

关键设计：

- `event: status` 驱动前端交互状态机（检索/生成/长等待）
- SSE 不支持断点续传（MVP 不做，断开则重新提问）
- `trace_id` 贯穿后端日志链路，便于用户报障

### 4.4 PostgreSQL Schema（核心 DDL）

```sql
-- 用户
CREATE TABLE users (
    user_id          VARCHAR(32) PRIMARY KEY,
    username         VARCHAR(64) UNIQUE NOT NULL,
    password_hash    VARCHAR(128) NOT NULL,
    role             VARCHAR(16) NOT NULL,            -- admin|employee|guest
    permission_level VARCHAR(8)  NOT NULL,            -- L1|L2|L3
    department       VARCHAR(64),
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at    TIMESTAMPTZ
);
CREATE INDEX idx_users_role ON users(role);

-- 文档（权威源）
CREATE TABLE documents (
    doc_id           VARCHAR(32) PRIMARY KEY,
    title            VARCHAR(256) NOT NULL,
    source_type      VARCHAR(32) NOT NULL,            -- local_upload
    source_url       TEXT,
    file_path        TEXT NOT NULL,
    file_hash        VARCHAR(64) NOT NULL,
    permission_level VARCHAR(8) NOT NULL,
    department       VARCHAR(64),
    chunk_count      INT NOT NULL DEFAULT 0,
    status           VARCHAR(16) NOT NULL,            -- pending|parsing|indexed|failed
    error_message    TEXT,
    uploaded_by      VARCHAR(32) REFERENCES users(user_id),
    uploaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_documents_status ON documents(status);
CREATE UNIQUE INDEX idx_documents_file_hash ON documents(file_hash);

-- 问答日志
CREATE TABLE qa_logs (
    log_id           VARCHAR(32) PRIMARY KEY,
    session_id       VARCHAR(32) NOT NULL,
    user_id          VARCHAR(32) NOT NULL REFERENCES users(user_id),
    scene            VARCHAR(16) NOT NULL,
    question         TEXT NOT NULL,
    answer           TEXT,
    intent           VARCHAR(32),
    entities         JSONB,
    sources          JSONB,
    tools_called     JSONB,
    confidence       VARCHAR(8),
    confidence_score NUMERIC(4,3),
    input_tokens     INT,
    output_tokens    INT,
    model_name       VARCHAR(32),
    cost_rmb         NUMERIC(10,4),
    response_time_ms INT,
    status           VARCHAR(16) NOT NULL,            -- success|fallback|error|permission_denied
    error_code       INT,
    trace_id         VARCHAR(32),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_qa_logs_user_created ON qa_logs(user_id, created_at DESC);
CREATE INDEX idx_qa_logs_session ON qa_logs(session_id);
CREATE INDEX idx_qa_logs_created ON qa_logs(created_at DESC);

-- 反馈
CREATE TABLE feedbacks (
    feedback_id      VARCHAR(32) PRIMARY KEY,
    log_id           VARCHAR(32) NOT NULL REFERENCES qa_logs(log_id),
    user_id          VARCHAR(32) NOT NULL REFERENCES users(user_id),
    feedback_type    VARCHAR(16) NOT NULL,
    reason           VARCHAR(32),
    comment          TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_feedbacks_log ON feedbacks(log_id);

-- 运行时配置（单行表）
CREATE TABLE qa_settings (
    id               INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    config           JSONB NOT NULL,
    updated_by       VARCHAR(32) REFERENCES users(user_id),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO qa_settings (id, config) VALUES (1, '{
  "rerank_enabled": true,
  "hallucination_threshold": 0.6,
  "max_context_docs": 5,
  "model_routing": {
    "answer_generation": "qwen-plus",
    "intent_recognition": "qwen-turbo"
  },
  "cost_daily_limit_rmb": 1000
}'::jsonb);
```

### 4.5 Redis Key 规范

| Key 模式 | 类型 | TTL | 用途 |
|---------|------|-----|------|
| `session:{session_id}` | Hash | 30min | 会话上下文缓存（压缩后历史 + 槽位） |
| `tokens:{yyyy-mm-dd}:{user_id}` | Counter | 7d | 单用户单日 token 累计 |
| `tokens:daily:{yyyy-mm-dd}` | Counter | 7d | 全局单日 token 累计（熔断用） |
| `ratelimit:{user_id}:{minute}` | Counter | 2min | 用户 QPS 限流 |
| `ratelimit:login:{username}` | Counter | 10min | 登录失败限流 |
| `lock:doc_sync:{doc_id}` | String | 5min | 知识同步分布式锁 |
| `jwt_blacklist:{jti}` | String | 剩余 exp | 登出后 jti 黑名单 |

### 4.6 错误码体系

| 段 | 含义 | 典型码 | 消息 |
|----|------|--------|------|
| 40000-40099 | 参数错误 | 40001 | 请求参数格式非法 |
| 40100-40199 | 认证 | 40101 | Token 失效 / 40102 账户禁用 |
| 40300-40399 | 权限 | 40301 | 无权访问该级别数据 |
| 42900 | 限流 | 42900 | 请求过于频繁 |
| 50001-50099 | LLM | 50001 | 大模型调用超时 |
| 50101-50199 | 检索 | 50101 | ES 服务不可达 |
| 50201-50299 | 嵌入 | 50201 | Embedder 异常 |
| 50301-50399 | 解析 | 50301 | 文档解析失败 |
| 50900 | 成本熔断 | 50900 | 当日成本已超阈值 |

统一错误包装：

```json
{
  "code": 50001,
  "message": "大模型服务超时",
  "trace_id": "tr_abc123",
  "fallback": {
    "answer": "系统繁忙...",
    "type": "template"
  }
}
```

---

## 5. RBAC 权限

### 5.1 JWT 声明结构

```json
{
  "sub": "u_001",
  "username": "zhangsan",
  "role": "employee",
  "pl": "L2",
  "dept": "HR",
  "iat": 1745330000,
  "exp": 1745330900,
  "jti": "jwt_xxx"
}
```

- 算法 HS256，`JWT_SECRET` 从 `.env` 注入（32 字节随机），不得硬编码
- access_token: 15min；refresh_token: 7d
- 登出后 jti 入 Redis 黑名单，TTL = 剩余 exp

### 5.2 鉴权依赖链

```python
# backend/app/api/deps.py
async def get_current_user(credentials, db) -> UserClaims:
    # 1. 解码 JWT（过期/签名错 → 40101）
    # 2. 查 Redis jwt_blacklist:{jti}
    # 3. 查 users.is_active=true（40102）
    # 4. 返回 UserClaims pydantic

def require_role(*allowed: str):
    async def _dep(claims = Depends(get_current_user)):
        if claims.role not in allowed:
            raise HTTPException(403, {"code": 40301, ...})
        return claims
    return _dep

require_admin    = require_role("admin")
require_any_user = require_role("admin", "employee", "guest")
```

### 5.3 RBAC 矩阵

| 角色 | L1 | L2 | L3 | 管理权限 |
|------|----|----|----|---------|
| guest | ✅ | ❌ | ❌ | 无 |
| employee | ✅ | ✅ | ❌ | 无 |
| admin | ✅ | ✅ | ✅ | 知识库/配置/日志 |

ABAC 的 `department` 字段保留但不参与匹配（代码注释标注，未来启用只需取消注释）。

### 5.4 ES Filter 前置过滤

```python
# backend/app/rbac/filter_builder.py
ROLE_LEVEL_MATRIX = {
    "guest":    ["L1"],
    "employee": ["L1", "L2"],
    "admin":    ["L1", "L2", "L3"],
}

def build_es_filter(claims: UserClaims) -> dict:
    allowed = ROLE_LEVEL_MATRIX[claims.role]
    return {"bool": {"filter": [{"terms": {"permission_level": allowed}}]}}
```

强约束：`hybrid_search` 工具入口强制合并该 filter，绕过即漏洞。单测用例：guest 请求必须过滤掉所有 L2/L3 内容（返回 0 条 L2/L3 chunk）。

### 5.5 权限拒绝与审计

| 场景 | HTTP | code | 用户提示 | 审计 |
|------|------|------|----------|------|
| 无 token / 过期 | 401 | 40101 | 请重新登录 | 不记录 |
| 角色不足 | 403 | 40301 | 您暂无权限查看此内容 | `qa_logs.status='permission_denied'` |
| 检索命中无权 chunk（理论不发生） | 500 | 50301 | 系统异常 | 严重告警 |

### 5.6 密码策略（MVP 简化）

- bcrypt cost=12
- 登录失败 5 次触发 `ratelimit:login:{username}` 限流 10min（HTTP 429）
- 种子数据 `scripts/seed_users.py` 创建 admin / employee / guest 3 个测试账户，部署前强制覆盖密码
- MVP **不做**：密码强度校验、密码重置流程、多因素、SSO/LDAP

---

## 6. 前端极简 Web UI

### 6.1 技术栈

Vite + React 18 + TypeScript + TailwindCSS + React Router + Zustand（流式会话）+ TanStack Query（CRUD 数据）+ axios。

### 6.2 页面清单（6 页）

| 路由 | 名称 | 权限 | 说明 |
|------|------|------|------|
| `/login` | 登录页 | 公开 | 用户名密码 |
| `/` | 对话主页 | 全员 | 流式问答核心界面 |
| `/history` | 历史会话 | 全员 | 侧边栏 + 会话详情（只读回放） |
| `/admin/knowledge` | 知识库管理 | admin | 上传/列表/删除/重索引 |
| `/admin/settings` | 系统配置 | admin | Rerank 开关等 |
| `/admin/logs` | 问答日志 | admin | 日志 + Token/成本聚合，手动刷新 |

`/admin/*` 通过 React Router guard + 菜单隐藏双重防线控制访问。

### 6.3 对话主页布局（ASCII 示意）

```
┌──────────────────────────────────────────────────────────┐
│  📚 企业知识库   🏠 对话 | 📜 历史 | ⚙ 管理 ▼   👤 张三 ▼ │
├──────────────┬───────────────────────────────────────────┤
│ 📜 会话列表   │  👋 欢迎！有什么可以帮你的？               │
│ ▶ 年假咨询    │  ┌─────────────────────────────┐         │
│   报销流程    │  │ 👤 公司的年假制度是怎样的？    │         │
│ [+ 新建会话]  │  └─────────────────────────────┘         │
│              │  ┌─────────────────────────────┐         │
│              │  │ 🔍 正在检索知识库... (status) │         │
│              │  └─────────────────────────────┘         │
│              │  ┌─────────────────────────────┐         │
│              │  │ 🤖 根据《员工手册》┃（流式）   │         │
│              │  │ 📎 员工手册V2.0·第3章第2节 [L2]│         │
│              │  │ 🎯 置信度：高 (92%)           │         │
│              │  │ 👍 👎  🔗 复制  🔁 重问        │         │
│              │  │ 💡 相关问题：如何申请？        │         │
│              │  └─────────────────────────────┘         │
├──────────────┴───────────────────────────────────────────┤
│ ⚠️ 答案仅供参考，重要决策请以官方文档或人工咨询为准        │
│ ┌──────────────────────────────────────┐  发送 ➤        │
│ │ 请输入问题...                          │                │
│ └──────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────┘
```

### 6.4 SSE 消费 Hook 与交互状态机

原生 `EventSource` 不支持 POST，用 `fetch + ReadableStream` 手写 SSE 解析：

```typescript
type ChatPhase = 'idle' | 'pending' | 'retrieving' | 'thinking' | 'streaming' | 'long_wait' | 'done' | 'error';

function useAskQuestion() {
  const [phase, setPhase] = useState<ChatPhase>('idle');
  const [streamText, setStreamText] = useState('');
  const [sources, setSources] = useState([]);
  const longWaitTimer = useRef<number>();

  async function ask(question: string, sessionId: string) {
    setPhase('pending');
    longWaitTimer.current = window.setTimeout(() => setPhase('long_wait'), 10000);
    const resp = await fetch('/api/v1/qa/ask', { method: 'POST', ... });
    const reader = resp.body!.pipeThrough(new TextDecoderStream()).getReader();
    // 解析 event: status / message / done / error
  }
  return { phase, streamText, sources, ask };
}
```

状态机对齐 PRD §8.1.6：

| phase | UI 表现 |
|-------|---------|
| pending | 输入框禁用 + 发送按钮 Loading |
| retrieving | 气泡上方 "🔍 正在检索知识库..." |
| streaming | "🤖 AI 正在思考..." + 光标闪烁打字机 |
| long_wait | "⏳ 系统处理中，请耐心等待" |
| done | 解锁输入框，渲染 sources + confidence |
| error | Toast + 兜底答案 |

### 6.5 Source 展示

`<SourceList>` 组件按 PRD §10.3.3：

```
📎 员工手册 V2.0 · 第 3 章第 2 节 | L2 级知识 | 更新 2025-01-15
```

点击 → 右侧抽屉展示 chunk 原文（引用句子黄色背景高亮）。原文通过 `GET /api/v1/qa/chunks/{chunk_id}` 按需加载，避免 SSE `done` 帧膨胀。

### 6.6 Admin 页面

- **`/admin/knowledge`**：拖拽上传 + 文档列表（状态条）+ 筛选（权限级/状态/上传人）+ 重索引/删除
- **`/admin/settings`**：Rerank 开关、幻觉阈值 Slider、Max context docs、日成本上限、模型路由；提交带 `updated_at` 乐观锁
- **`/admin/logs`**：顶部四卡（今日问答数/成功率/平均响应时间/今日 Token 成本）+ 日志表 + 筛选 + 单条详情抽屉；**手动刷新按钮**（无轮询）

### 6.7 响应式、无障碍、免责声明

- 响应式：Tailwind `md:` 断点，桌面双栏 / 移动单栏
- 无障碍：按钮 `aria-label`，流式区 `aria-live="polite"`
- 键盘：Ctrl/⌘ + Enter 发送、Esc 取消、↑ 引用上一次问题
- 免责声明常驻对话页底部：

> ⚠️ 本系统基于企业知识库提供智能问答服务，答案仅供参考。重要决策请以官方文档或人工咨询为准。

---

## 7. 非功能性：可观测、降级、测试、部署

### 7.1 可观测三件套

**结构化日志**（structlog + python-json-logger）：所有日志统一字段 `ts/level/logger/trace_id/session_id/user_id/event/...`。`trace_id` 在 FastAPI middleware 生成，贯穿整条请求链（含工具调用、ES/LLM 日志），SSE `done` 帧也带回前端。

**Metrics（Prometheus）**：通过 `prometheus_fastapi_instrumentator` 暴露 `/metrics`：

| 指标 | 类型 | 标签 | 用途 |
|------|------|------|------|
| `http_requests_total` | Counter | method/path/status | QPS / 错误率 |
| `http_request_duration_seconds` | Histogram | path | P50/P95/P99 |
| `qa_tool_duration_seconds` | Histogram | tool | 工具层耗时分解 |
| `qa_llm_tokens_total` | Counter | model/direction | Token 消耗 |
| `qa_llm_cost_rmb_total` | Counter | model | 成本累计 |
| `qa_confidence_bucket` | Histogram | - | 置信度分布 |
| `qa_fallback_total` | Counter | reason | 兜底触发次数 |

Prometheus + Grafana 放进 docker-compose 的 `monitoring` profile（默认不启动）。

**Tracing**：MVP 不上 OTel Jaeger，依赖 `trace_id` + 日志聚合。接口保留，未来可插入。

### 7.2 错误处理与降级矩阵

| 触发点 | 降级动作 | SSE 呈现 | 告警 |
|--------|----------|----------|------|
| LLM 首 token >5s | Provider 切换：Qwen-Plus → DeepSeek | 继续流式无感 | `qa_fallback{reason="llm_timeout_switch"}` |
| LLM 连续失败 3 次 | 模板答案 + 人工客服建议 | `event: error` + `fallback.answer` | P1 |
| Embedder 异常 | 降级为纯 BM25 | 正常答案 + 标签 | P2 |
| ES 不可达 | 兜底答案 + 显眼错误 | `event: error` (50101) | P0 |
| 置信度 <0.6 | 改写为"无法确定"模板 | `confidence: "low"` | 记日志 |
| 单日成本 >¥1000 | 切 Qwen-Turbo 低成本模型 | 无感 | P1 + 邮件 |
| 单日成本 >¥5000 | 拒绝新请求，50900 | `event: error` (50900) | P0 + 短信 |
| 单用户 >¥50 | 限流用户 | HTTP 429 | 记日志 |

**降级判定中心**：`backend/app/harness/degrade.py` 单例 `DegradeState`，每次工具调用前 `check()`，被熔断时直接返回降级 `ToolResult`。状态来源 Redis 计数器（跨实例一致）。

### 7.3 测试策略

| 层级 | 框架 | 覆盖内容 | 覆盖率 |
|------|------|----------|--------|
| 单元测试 | pytest + pytest-asyncio | 工具/Provider/Chunker/FilterBuilder/PromptRenderer | > 80% |
| 契约测试 | pytest + respx | LLM Provider 对 DashScope/DeepSeek API schema | 100% |
| 集成测试 | pytest + testcontainers | 真实 PG + ES + Redis，端到端 | 5 条主干 |
| 评测测试 | 自建 runner + 评测集 | 冒烟 50 组 + 黄金 500 组 | 准确率 >85% / 召回 >80% |
| 前端测试 | Vitest + React Testing Library | 组件 + SSE hook | > 70% |
| E2E 测试 | Playwright | 登录→问答→查看来源→反馈 | 3 条冒烟 |

**冒烟评测集**：从 PRD 5 大场景各挑 10 组共 50 组（MVP 阶段）。黄金 500 组留作内测期收集。

**CI**（`.github/workflows/ci.yml`）：
1. ruff + black check
2. mypy strict
3. pytest unit + contract
4. docker compose up & 集成测试
5. 前端 vitest + tsc

### 7.4 性能基线

压测：`locust` 100 并发 × 5min 混合负载（问答 80% / 上传 10% / 管理 10%）。

| 指标 | 目标 |
|------|------|
| 单次问答 P50 | < 3s |
| 单次问答 P95 | < 10s |
| ES hybrid_search P95 | < 300ms |
| Embedder 单 query P95 | < 200ms |
| Rerank Top-20 P95 | < 500ms |
| 并发 100 成功率 | > 99% |

不达标时通过 `qa_tool_duration_seconds` 分桶定位哪个工具超标，针对性优化。

### 7.5 部署与运维

**`docker-compose.yml` 结构**：

```yaml
services:
  postgres:       # 16-alpine，挂 ./data/pg
  elasticsearch:  # infinilabs/elasticsearch-ik:8.11，挂 ./data/es
  redis:          # 7-alpine，挂 ./data/redis
  backend:        # 自建镜像，挂 ./backend/data + ./backend/app（dev）
  frontend:       # nginx:alpine 托管 dist/

profiles:
  monitoring:
    prometheus:
    grafana:
```

**`deploy.sh`**（对齐 CLAUDE.md）：

```bash
deploy.sh start        # docker compose up -d
deploy.sh stop         # docker compose down
deploy.sh logs <svc>   # docker compose logs -f <svc>
deploy.sh ps           # docker compose ps
deploy.sh init         # 首次初始化：建 ES 索引、Alembic migrate、seed users
deploy.sh reindex      # 离线重建 ES 索引
deploy.sh monitoring   # 启 monitoring profile
```

**环境配置**：`.env.example` 列全 `DATABASE_URL / ES_URL / REDIS_URL / DASHSCOPE_API_KEY / DEEPSEEK_API_KEY / JWT_SECRET / DATA_DIR`，启动时用 pydantic-settings 校验，缺失 fail-fast。

**备份策略（MVP 最小集）**：

- PG：每日 `pg_dump` 到 `backend/data/backups/YYYY-MM-DD.sql`，保留 7 天
- ES：不做 snapshot，丢失时 `deploy.sh reindex` 从 PG 原始文档重建
- Disk data：依赖宿主机备份

### 7.6 MVP 验收标准（Definition of Done）

**硬门**（任一不达 → 不发布）：

- [ ] 冒烟评测集（50 组）准确率 ≥ 85%（三人评分均值）
- [ ] Top-5 召回率 ≥ 80%
- [ ] 权限越权拦截 100%（guest 请求 L2/L3 返回 0 条）
- [ ] 单次问答 P95 ≤ 10s（100 并发 locust）
- [ ] 并发 100 成功率 ≥ 99%
- [ ] 所有工具有单测，CI 通过
- [ ] docker compose up 后 5 分钟内完成"登录→上传 PDF→提问→看到答案和来源"

**软门**（加分，不阻塞）：

- [ ] 置信度标注与人工打分相关系数 > 0.7
- [ ] SSE 首字延迟 P50 ≤ 1.5s
- [ ] 管理日志页展示完整 `trace_id` 链路

### 7.7 MVP **不做**清单

- 客服工单 / 营销话术 / 运维支持 3 个 Agent（第二期）
- 飞书 / OA / 设备台账接入（第二期）
- OCR / ASR / 视频解析（第二期）
- 移动端原生 App / 多语言 / 复杂审批
- SSE 断点续传（方案留）
- OTel 分布式追踪（接口留）
- K8s Helm Chart（docker-compose 起）
- 本地 vLLM 部署（Provider 接口已留）
- 知识图谱 / 长期记忆表（PRD §12.1.2 二级记忆表留坑）
- 内容安全审核（涉政/涉黄外部审核服务，MVP 仅依赖模型自身安全防线）
- 密码强度校验 / 密码重置 / 多因素 / SSO/LDAP

---

## 8. 风险与依赖

### 8.1 技术风险

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| ES 冗余字段与 PG 不一致 | 中 | 中 | 双写先 PG 后 ES + 重试 + `reindex.py` 兜底 |
| 大模型幻觉 | 高 | 中 | 置信度评估 + 溯源 + 低分兜底模板 |
| 云 API 调用失败/超时 | 中 | 中 | Provider 抽象 + 降级切换 + 本地 vLLM 预留 |
| Rerank CPU 吞吐不足 | 中 | 中 | 可一键关闭 / 异步批处理 |
| 权限 filter 绕过 | 高 | 低 | 主循环强注入 + 单测锁住 + 代码评审 |
| BGE-M3 本地模型加载内存 | 中 | 低 | 单实例启动一次、全局复用、懒加载 |

### 8.2 项目依赖

| 依赖项 | 风险等级 | 缓解 |
|--------|---------|------|
| DashScope API | 中 | DeepSeek 备用 Provider |
| ES 8.11 + IK 插件 | 低 | 镜像已打包 |
| BGE-M3 模型权重 | 低 | HuggingFace 下载，可离线打镜像 |
| PostgreSQL 16 | 低 | 官方镜像 |

---

## 9. 分期路线（本 Spec 外）

- **Phase 1（本 MVP）**：KnowledgeQA Agent + RAG 闭环 + 极简前端 + Docker Compose 部署
- **Phase 2**：ServiceTicket / OpsSupport 两个 Agent + 飞书/OA 接入 + OCR/ASR
- **Phase 3**：SalesContent Agent + 长期记忆 + 知识图谱 + K8s Helm + 移动端适配
- **Phase 4**：多租户 / 多语言 / 子 Agent 编排 / FSM 握手协议启用

---

## 10. 批准签名

- 产品负责人：______（待签）
- 技术负责人：______（待签）
- 测试负责人：______（待签）
- 批准日期：______

---

**—— 本 Spec 结束 ——**
