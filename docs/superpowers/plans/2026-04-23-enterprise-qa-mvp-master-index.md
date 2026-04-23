# Enterprise Knowledge QA MVP — Master Plan Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each phase plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分阶段交付企业知识库问答系统 MVP，单 Agent + RAG 端到端闭环。每个阶段独立可测、可回归。

**源 Spec:** `docs/superpowers/specs/2026-04-23-enterprise-knowledge-qa-mvp-design.md`（commit `fbec4a3`）

**Architecture:** 按 Spec §1.1 分层：Frontend → FastAPI → Harness Core → Tools/Providers/Knowledge → Storage（PG + ES + Redis + Disk）。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2 async / Alembic / ES 8.11 + IK / Redis 7 / BGE-M3 / Vite + React 18 / Docker Compose。

---

## 执行顺序与依赖

```
Phase 1 基础设施
    └── Phase 2 鉴权 & RBAC
            └── Phase 3 知识管线
                    └── Phase 4 Harness 核心 & 工具
                            └── Phase 5 QA API + SSE
                                    └── Phase 6 前端
                                            └── Phase 7 评测 & 部署收尾
```

前序阶段未达 DoD 时**不得**启动下一阶段。

---

## 阶段清单

### Phase 1：基础设施（Foundation）

**文件：** `docs/superpowers/plans/2026-04-23-phase1-foundation.md`
**产出：** docker-compose 一键启动 PG/ES/Redis + FastAPI 骨架（/healthz）+ Alembic 所有 DDL + 前端脚手架 + deploy.sh。
**DoD：**
- `./deploy.sh start` 后 60 秒内 `./deploy.sh ps` 全部 healthy
- `GET /healthz` 返回 200
- Alembic `upgrade head` 建出 5 张表 + qa_settings 默认行
- ES `qa_chunks` 索引创建成功（含 1024 维 dense_vector + IK 分词）
- `seed_users.py` 插入 admin/employee/guest 三个账户
- CI 跑通 ruff + pytest + 前端 tsc

### Phase 2：鉴权 & RBAC

**文件：** `docs/superpowers/plans/2026-04-23-phase2-auth-rbac.md`（待写）
**依赖：** Phase 1
**产出：** `/api/v1/auth/{login,refresh,logout}` + JWT 生成/验证 + Redis jti 黑名单 + `require_role` 依赖 + `build_es_filter`。
**DoD：**
- pytest 覆盖登录成功/失败/过期/黑名单
- guest/employee/admin 对 `/admin/*` 的拦截集成测试通过
- `build_es_filter(guest)` 过滤 L2/L3 的单测锁住
- bcrypt cost=12 实锤

### Phase 3：知识管线

**文件：** `docs/superpowers/plans/2026-04-23-phase3-knowledge-pipeline.md`（待写）
**依赖：** Phase 1, 2
**产出：** Parsers（PDF/DOCX/MD/TXT）+ Chunker + Embedder（BGE-M3）+ Reranker + Indexer + `POST /api/v1/knowledge/upload` + `scripts/reindex.py`。
**DoD：**
- 上传 10MB PDF 后 chunks 入 ES，`chunk_id` 幂等
- Embedder 1024 维归一化单测通过
- `scripts/reindex.py` 从 PG 原文重建 ES 通过
- ES 检索 BM25 + knn 双路返回预期结果
- `rerank` 开/关切换对结果顺序影响可见

### Phase 4：Harness 核心 + 工具 + Providers

**文件：** `docs/superpowers/plans/2026-04-23-phase4-harness-tools.md`（待写）
**依赖：** Phase 1, 2, 3
**产出：** `agent_loop.py` + `tool_registry.py` + `context.py` + `session_store.py` + `degrade.py` + 6 个工具 + DashScope/DeepSeek Provider + Prompt 模板。
**DoD：**
- `run(query, session_id, user_claims)` 返回流式 Event 链路
- MAX_STEPS=10 触发超限退出单测通过
- Session JSONL append-only 正确写入 `data/sessions/YYYY-MM-DD/`
- Provider contract test（respx）覆盖 DashScope/DeepSeek 正常 + 超时 + 切换
- 微压缩 + 自动压缩（>3000 token）单测通过
- 幻觉检测阈值 0.6 兜底路径单测通过

### Phase 5：QA API + SSE

**文件：** `docs/superpowers/plans/2026-04-23-phase5-qa-api-sse.md`（待写）
**依赖：** Phase 1, 2, 3, 4
**产出：** `POST /api/v1/qa/ask` (SSE) + `/qa/sessions/{id}` + `/qa/chunks/{id}` + `/feedback` + `/admin/{settings,logs,metrics}` + structlog trace_id middleware + 错误码中间件。
**DoD：**
- httpx 集成测试走通 SSE 帧序列（status → message → done）
- `event: error` + fallback 路径覆盖 LLM 超时 / ES 不可达 / 成本熔断
- 100 并发 locust 成功率 ≥ 99%，P95 ≤ 10s
- `/metrics` 暴露 Prometheus 指标
- trace_id 贯穿日志与响应帧

### Phase 6：前端

**文件：** `docs/superpowers/plans/2026-04-23-phase6-frontend.md`（待写）
**依赖：** Phase 1, 2, 5
**产出：** 6 个页面（login / chat / history / admin\*3）+ Zustand 流式状态机 + TanStack Query CRUD + `useSSE` Hook + ChatBubble / SourceList / ConfidenceBadge 组件。
**DoD：**
- Vitest 覆盖率 ≥ 70%
- Playwright E2E 登录→问答→查看来源→反馈 通过
- 响应式 + a11y 基础检查（aria-label / aria-live）
- Ctrl+Enter 发送、Esc 取消、↑ 引用快捷键可用
- `/admin/*` 双重防线（router guard + 菜单隐藏）验证

### Phase 7：评测 & 部署收尾

**文件：** `docs/superpowers/plans/2026-04-23-phase7-eval-devops.md`（待写）
**依赖：** Phase 1-6
**产出：** 冒烟评测集（50 组）+ 评测 runner + locust 压测脚本 + Grafana dashboard + 备份脚本 + 灾难恢复手册。
**DoD：**
- Spec §7.6 所有硬门全部勾选
- 评测集准确率 ≥ 85%，召回 ≥ 80%
- `deploy.sh monitoring` 起 Prometheus + Grafana
- PG 每日 `pg_dump` 备份 + 保留 7 天验证
- 文档：`docs/operations/{runbook,disaster-recovery}.md`

---

## 滚动交付规则

1. 每 Phase 完成后，用户审查 → 合入 main → 再启动下一 Phase 的 writing-plans。
2. 每 Phase 在独立分支（或 worktree）开发，通过 DoD 才合入 main。
3. 如果发现前序 Phase 设计缺陷，**先回滚**再修正 Spec，而不是在当前 Phase 打补丁。
4. 每 Phase 完成触发 `recording-iteration-history` 技能记录 CHANGELOG。

---

**当前状态：** Phase 1 Foundation 的详细 plan 已生成（同目录 `2026-04-23-phase1-foundation.md`），其余阶段等 Phase 1 跑通后滚动撰写。
