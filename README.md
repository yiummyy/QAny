# QAny — 企业级智能问答系统

基于 RAG（检索增强生成）的企业知识库问答平台，支持多场景 Agent 扩展。

## 技术栈

| 层 | 技术 |
|---|------|
| **前端** | React 18 + TypeScript + Vite + Tailwind CSS + Zustand + React Query |
| **后端** | Python 3.11+ / FastAPI / SQLAlchemy 2.0 (async) / Pydantic v2 |
| **数据库** | PostgreSQL 16 / Redis 7 |
| **搜索引擎** | Elasticsearch 8.11 (BM25 + KNN + RRF 混合检索) |
| **AI/模型** | BGE-M3 Embedding / BGE-Reranker-v2-m3 / Qwen-Plus (DashScope) / DeepSeek |
| **基础设施** | Docker Compose / Nginx / Prometheus + Grafana (可选) |

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repo-url> && cd QAny

# 配置环境变量（从模板复制）
cp .env.example .env
# 编辑 .env：填写 DASHSCOPE_API_KEY（必填）等
```

### 2. 启动服务

```bash
./deploy.sh start
```

首次启动会自动拉取镜像并构建。启动后等待健康检查通过（约 30-60 秒）。

### 3. 初始化

```bash
./deploy.sh init
```

这一步会执行数据库迁移、创建 ES 索引、写入种子用户。

### 4. 访问

| 入口 | 地址 |
|------|------|
| 前端界面 | http://localhost |
| 后端 API 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/healthz |

### 默认账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | admin | admin123 |
| 员工 | employee | emp123 |
| 访客 | guest | guest123 |

## 常用命令

```bash
./deploy.sh start          # 启动所有服务
./deploy.sh stop           # 停止所有服务
./deploy.sh restart <svc>  # 重启指定服务
./deploy.sh ps             # 查看服务状态
./deploy.sh logs <svc>     # 查看日志（不指定则全量）
./deploy.sh health         # 健康检查
./deploy.sh reindex [id]   # 重建 ES 索引
./deploy.sh backup         # 备份数据库
./deploy.sh init           # 初始化（迁移 + ES 索引 + 种子用户）
```

## 项目结构

```
QAny/
├── frontend/                 # React 前端 (Vite + TypeScript)
│   └── src/
│       ├── components/       # UI 组件
│       ├── pages/            # 页面路由
│       ├── stores/           # Zustand 状态管理
│       └── api/              # Axios API 客户端
├── backend/                  # Python 后端 (FastAPI)
│   ├── app/
│   │   ├── api/v1/           # REST API 路由
│   │   ├── harness/          # Agent 循环引擎 & RAG 管线
│   │   ├── tools/            # Agent 工具（检索 / 工单 / 升级）
│   │   ├── providers/        # LLM 提供商适配层
│   │   ├── knowledge/        # Embedding & Reranker
│   │   ├── models/           # SQLAlchemy 数据模型
│   │   ├── storage/          # ES / PG / Redis 客户端
│   │   ├── prompts/          # Prompt 模板
│   │   ├── auth/             # JWT 鉴权
│   │   └── rbac/             # 基于角色的权限控制
│   ├── migrations/           # Alembic 数据库迁移
│   ├── scripts/              # 运维脚本（init / seed / reindex）
│   └── tests/                # 测试（unit / integration / contract / eval）
├── docs/superpowers/         # 项目文档
│   ├── specs/                # 技术规范
│   └── plans/                # 研发计划
├── docker-compose.yml        # 服务编排
├── deploy.sh                 # 部署脚本入口
└── .env.example              # 环境变量模板
```

## 核心架构

### Agent + RAG 管线解耦

```
用户问题 → API (scene → agent 路由) → Agent Loop (plan → 选择工具)
                                           │
                          ┌────────────────┼──────────────────┐
                          ▼                                   ▼
                   query_knowledge                      create_ticket
                   ┌──────────────────────────┐         lookup_ticket
                   │ ① rewrite_query          │         escalate
                   │    · 多轮对话指代消解      │         ...
                   │    · 意图识别 (6类)        │
                   │    · 实体抽取             │
                   │ ② hybrid_search           │
                   │    · BM25 + KNN + RRF     │
                   │    · RBAC 权限过滤        │
                   │    · entity 加权检索      │  ← 实体驱动精确匹配
                   │ ③ BGE-Reranker 重排      │
                   │ ④ 权限二次校验            │
                   │ ⑤ generate_answer        │
                   └──────────────────────────┘
                          │
                          ▼
                     Agent 评估结果 → intent 驱动决策
                     · 制度查询 → final_answer
                     · 故障排查 → create_ticket / escalate
                     · 检索不足 → 换 query 重搜 / 降级回答
                          │
                          ▼
                     final_answer → hallucination_check → SSE 流式 → 用户
```

- **Agent**：负责高层决策 + 意图驱动路由（搜不搜？重搜？开不开工单？）
- **RAG Pipeline**：固定 5 步管线，确定性执行，不可被 Agent 跳过或重排
- **多场景**：通过 `AgentConfig` 配置不同工具集、知识库索引、Prompt 模板
- **智能检索**：实体抽取反馈到 ES multi_match 加权，多轮对话历史注入 rewrite 消解指代

### Agent 场景

| Agent | 场景值 | 知识库索引 | 专属工具 | 状态 |
|-------|--------|-----------|---------|------|
| KnowledgeQA | general / knowledge | qa_chunks | — | ✅ 已实现 |
| ServiceTicket | ticket / service | ticket_knowledge | create_ticket, lookup_ticket, escalate | ✅ 已实现 |
| SalesContent | sales | sales_knowledge | search_crm, generate_proposal | 🔜 预留框架 |
| OpsSupport | ops | ops_knowledge | query_monitoring, run_diagnostic, escalate | 🔜 预留框架 |

### 权限模型

| 角色 | 权限级别 | 可访问文档 |
|------|---------|-----------|
| admin | L3 | L1 / L2 / L3 |
| employee | L2 | L1 / L2 |
| guest | L1 | L1 |

## 设计文档

| Spec | 日期 | 说明 |
|------|------|------|
| [MVP 设计稿](docs/superpowers/specs/2026-04-23-enterprise-knowledge-qa-mvp-design.md) | 2026-04-23 | 原始架构设计、API 契约、RBAC 模型 |
| [RAG 管线 + Agent 解耦重构](docs/superpowers/specs/2026-04-27-rag-pipeline-agent-refactor.md) | 2026-04-27 | AgentConfig 多场景、固定 RAG 管线、两层工具注册 |
| [意图改写 + 实体过滤增强](docs/superpowers/specs/2026-04-27-intent-rewrite-entity-enhancement.md) | 2026-04-27 | 多轮历史注入、意图驱动决策、实体加权检索 |

## 开发指南

### 后端

```bash
cd backend
pip install -e ".[dev]"
pytest tests/ -v                    # 运行测试
ruff check .                        # 代码检查
```

### 前端

```bash
cd frontend
npm install
npm run dev                         # 开发服务器 (localhost:5173)
npm run build                       # 生产构建
npm run typecheck                   # TypeScript 类型检查
```

## License

Internal use — all rights reserved.
