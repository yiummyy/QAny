# BadCase 记录

## 1. ES 索引中文分词失效导致 BM25 全军覆没

> **一句话**：ES 动态映射未安装 IK 中文分词器，中文被逐字拆分，BM25 关键词检索全部失效——连文档名都搜不到。
> **修复**：运行 `init_es.py` 重建索引（ik\_max\_word），`content`/`doc_name`/`section` 启用 IK 分词。

### 问题表现

用户提问"去年有哪些基于客户的新业务规则？"，系统返回兜底文案：

> 抱歉，我无法回答这个问题，因为提供的参考文档中没有任何关于去年基于客户的新业务规则的信息。

但知识库中 `欧保顺耀业务规则2.0版.pdf` 包含大量客户、业务规则相关内容，应有命中。

### 排查过程

1. **确认文档已入库**：查询 ES `qa_chunks` 索引，`doc_name.keyword=欧保顺耀业务规则2.0版.pdf` 返回 9 条 chunks，含"客户范围""KA 客户""业务规则"等内容，证明文档已正常索引。
2. **测试 BM25 直接检索**：
   ```
   查询 "去年有哪些基于客户的新业务规则"  → 0 hits   ← 致命
   查询 "客户 业务规则"                   → 0 hits
   查询 "欧保顺耀"                       → 0 hits   ← 连文档名都搜不到
   查询 "KA客户"                        → 0 hits
   ```
   全量词/关键词/文档名均返回 0，排除查询改写问题，定位到**分词层面**。
3. **检查索引 mapping**：
   ```
   content:  type=text, analyzer=default   ← 应该是 ik_max_word
   doc_name: type=text, analyzer=default
   section:  type=text, analyzer=default
   tags:     type=text, analyzer=default   ← 应该是 keyword
   ```
   所有字段的 analyzer 都是 `default`（standard 标准分词器），而不是 IK 中文分词器。
4. **对比分词器输出**：
   | 分词器                                                             | "去年有哪些基于客户的新业务规则"                                         |
   | --------------------------------------------------------------- | --------------------------------------------------------- |
   | `ik_max_word`                                                   | 去年 / 年有 / 哪些 / 基于 / 客户 / 的 / 新 / 业务 / 规则                  |
   | `standard`                                                      | 去 / 年 / 有 / 哪 / 些 / 基 / 于 / 客 / 户 / 的 / 新 / 业 / 务 / 规 / 则 |
   | **Standard 分词器将中文逐字拆分，"客户"→"客/户"，倒排索引中不存在"客户"这个词，BM25 永远无法命中。** | <br />                                                    |

### 根因

`scripts/init_es.py` 定义了正确的 IK 分词器 mapping，但**从未被执行**。ES 索引在首次 `index_chunks()` 调用时由动态映射自动创建，所有字段默认使用 standard 分词器。

**关键设计缺陷**：`index_chunks()` 没有在写入前检查索引是否存在及 mapping 是否合法。系统依赖运维人员手动运行 `init_es.py`，但部署文档中缺少此步骤。

### 连带问题

1. **`delete_doc_chunks()`** **未传** **`knowledge_base`**（[knowledge.py:316](backend/app/api/v1/knowledge.py#L316)）：
   - `delete_document()` 调用 `delete_doc_chunks(doc_id)` 默认 `knowledge_base="qa"`
   - 删除 ticket/sales/ops 库文档时会去错误的索引删除
   - 修复：传入 `doc.knowledge_base`
2. **`delete_doc_chunks()`** **索引不存在时抛 404**（[indexer.py:24](backend/app/knowledge/indexer.py#L24)）：
   - 修复：try/except 包裹，索引不存在时返回 0
3. **Intent recognition 模型路由到推理模型**：
   - 日志：`model_routing[intent_recognition]=qwen-turbo incompatible with base_url=https://api.deepseek.com, using primary model=deepseek-reasoner`
   - 推理模型（deepseek-reasoner）输出推理链格式而非纯 JSON，`rewrite_query` 解析失败，退化到原始 query
   - 即使本次排查中分词器修复（纯 BM25 已能命中），配置了 DashScope API key 可进一步解决此问题
4. **`tags`** **被动态映射为** **`text`** **类型**：
   - 标签"差旅交通"被作为文本分词为多个字符，导致标签匹配（`_build_tag_clauses`）和显示出现编码问题
   - 修复：`init_es.py` 中将 `tags` 和 `knowledge_base` 显式声明为 `keyword`

### 解决方案

1. **更新** **`init_es.py`**：
   - `ik_smart` → `ik_max_word`（检索场景高召回优先）
   - 补充缺失字段映射：`content_type`、`page`、`tags`、`knowledge_base`
   - `doc_name` 和 `section` 改为 text + IK 分词器（原为 keyword，无法模糊搜索中文名称）
2. **操作步骤**：
   ```bash
   # 1. 删除旧索引（用 dynamic mapping 创建的）
   docker compose exec backend python -c "
   from app.storage.es_client import get_es
   es = get_es()
   for name in ['qa_chunks','ticket_knowledge','sales_knowledge','ops_knowledge']:
       if await es.indices.exists(index=name):
           await es.indices.delete(index=name)
   "

   # 2. 用 IK 分词器重建索引
   docker compose exec backend python scripts/init_es.py

   # 3. 重建所有文档索引
   curl -X POST /api/v1/knowledge/sync  # 触发所有文档重新处理
   ```

### 修复后效果

| 查询                | 修复前    | 修复后                            |
| ----------------- | ------ | ------------------------------ |
| `去年有哪些基于客户的新业务规则` | 0 hits | **47 hits** (top score: 8.00)  |
| `客户 业务规则`         | 0 hits | **30 hits** (top score: 7.43)  |
| `欧保顺耀`            | 0 hits | **23 hits** (top score: 10.40) |
| `差旅交通 住宿标准`       | 0 hits | **18 hits** (top score: 17.80) |

### 防御措施建议

- **P0**：在 `index_chunks()` 中首次写入前调用 `ensure_index()`，确保索引 mapping 正确
- **P0**：deploy 脚本/README 中增加 `python scripts/init_es.py` 初始化步骤
- **P1**：`rewrite_query` 的 stage provider 配置增加 DeepSeek 兼容的意图识别模型（如 deepseek-chat）
- **P2**：增加 `POST /api/v1/admin/health/indices` 健康检查端点，探测各索引的 analyzer 配置

***

## 2. deepseek-reasoner 推理模型导致全链路 LLM 调用失败 (2026-05-10)

> **一句话**：推理模型 deepseek-reasoner 输出 reasoning\_content 耗尽 max\_tokens 导致 content 为空，Plan 与 rewrite 全线崩溃，FallbackPlanner 接管后给出低质量兜底回答。
> **修复**：`llm_model` 切 `deepseek-chat`，`model_routing` 全部对齐为兼容模型。

### 问题表现

ES 分词器修复后，检索已正常（BM25 返回 47 hits），但用户提问"去年有哪些基于客户的新业务规则？"仍然得到兜底文案：

> 您好，我无法从您提供的参考文档中找到关于"去年基于客户的新业务规则"的具体信息。

### 排查过程

1. **检查后端日志**：
   ```
   model_routing[intent_recognition]=qwen-turbo incompatible → falls back to deepseek-reasoner
   tool_timeout name=search_knowledge attempt=1/2 retry_in=1s
   Plan provider failed (stage=plan): API 返回空 content (model=deepseek-reasoner)
   ```
   两个关键信号：
   - `search_knowledge` 频繁超时（15s 不够用）
   - Plan 阶段直接报 `API 返回空 content`
2. **检查 DB 配置**：
   ```json
   {
     "llm_model": "deepseek-reasoner",
     "model_routing": {
       "answer_generation": "qwen-plus",
       "intent_recognition": "qwen-turbo"
     }
   }
   ```
3. **确认** **`model_routing`** **中的 qwen 模型全部不兼容**：

   `_model_mismatch()` 检测到 `qwen-turbo`/`qwen-plus` 不以 `deepseek-` 开头，判定不兼容 DeepSeek API，全部回退到 primary model，即 `deepseek-reasoner`。

### 根因

**`deepseek-reasoner`** **是推理模型（类似 DeepSeek-R1），输出分两段**：

- `reasoning_content`：思考链（消耗大量 token）
- `content`：最终答案

**`DeepSeekProvider.chat()`** **只读取** **`choices[0].message.content`，不处理** **`reasoning_content`。在** **`max_tokens=500`（plan）的限制下，推理链占满全部 token →** **`content`** **为空 →** **`RuntimeError("API 返回空 content")`。**

**连锁反应**：

```
rewrite_query (search_knowledge 内部):
  deepseek-reasoner, max_tokens=2000
  → 推理链消耗 1800+ tokens → content 只有 100+ tokens
  → 或推理链过长导致 15s 超时 → 整个 search_knowledge 超时

plan (agent_loop 每步):
  deepseek-reasoner, max_tokens=500
  → 推理链消耗全部 500 tokens → content 为空
  → Plan provider 连续失败 → 触发 FallbackPlanner
  → 硬编码路径缺少诊断信息，直接进入 generate_answer
  → 低质量答案
```

这与 BadCase #1 叠加时尤为严重：即使检索已修复，LLM 层全线崩溃仍导致回答质量极差。

### 修复

```sql
UPDATE qa_settings SET config = '{
  "llm_model": "deepseek-chat",
  "llm_provider": "deepseek",
  "model_routing": {
    "answer_generation": "deepseek-chat",
    "intent_recognition": "deepseek-chat"
  },
  ...
}' WHERE id = 1;
```

- `llm_model`: `deepseek-reasoner` → `deepseek-chat`
- `model_routing.intent_recognition`: `qwen-turbo` → `deepseek-chat`
- `model_routing.answer_generation`: `qwen-plus` → `deepseek-chat`

### 防御措施

- **P0**：`DeepSeekProvider.chat()` 应检测 `reasoning_content` 存在且 `content` 为空的情况，给出明确错误提示而非通用 "API 返回空 content"
- **P1**：`_build_provider_router()` 应在 provider 是 `deepseek` 时自动将 `model_routing` 中不兼容的模型名替换为 DeepSeek 兼容等价物，而非全部回退到 primary
- **P1**：Plan `max_tokens` 从 500 增加到 800，防止深度思考模型耗尽 token

***

## 3. `agent_loop.session_store` 不存在导致会话/历史 API 500 (2026-05-10)

> **一句话**：`qa.py` 通过 `agent_loop.session_store` 间接访问 session 存储，但 `agent_loop.py` 未将 `session_store` 导出为模块属性，`AttributeError` 导致 500。
> **修复**：`qa.py` 直接从 `session_store` 模块导入 `get_history`。

### 问题表现

刷新页面后，"对话"和"历史"两个栏目全部空白。`GET /api/v1/qa/sessions/{id}` 返回 500。

### 根因

[qa.py:376](backend/app/api/v1/qa.py#L376) 通过 `agent_loop.session_store.get_history()` 访问 session\_store，但 `agent_loop.py` 只从 `session_store` 导入了 3 个函数（`append`、`make_task_id`、`save_task`），既没有 `import session_store` 模块引用，也没有导入 `get_history`。

```
AttributeError: module 'app.harness.agent_loop' has no attribute 'session_store'
```

### 修复

在 `qa.py` 中直接从 `session_store` 导入 `get_history`：

```python
from app.harness.session_store import get_history
records = await get_history(session_id)
```

### 防御措施

- **P1**：`agent_loop.py` 应显式导出 `session_store` 作为模块属性，供外部统一入口访问
- **P1**：CI 中增加 `GET /api/v1/qa/sessions/{id}` 的集成测试

***

## 4. search\_knowledge 频繁超时 + Plan LLM 决策混乱导致首 Token 延迟 5-10s 及第二轮回答失败 (2026-05-10)

> **一句话**：Plan LLM 用相同 args 并行调用两次 search\_knowledge + rewrite\_query LLM 超时 + 跳过 generate\_answer，五因素叠加致首 Token 延迟 5-10s 且第二轮直接"无法确定"。
> **修复**：search\_knowledge timeout 15s→30s，rewrite\_query 独立 5s 超时降级，代码层去重，Plan 前移除已成功工具程序化推进 search→generate→final。

### 问题表现

1. 首 Token 延迟 5-10 秒
2. 第二轮对话检索耗时更长，并直接给出"无法确定答案"
3. 日志中频繁出现 `tool_timeout name=search_knowledge`

### 排查过程

1. **检查流水线日志**：
   ```
   plan step=0 decision=tool_call tool=None
   Step 0: parallel calling 2 tools: ['search_knowledge', 'search_knowledge']
   tool_timeout name=search_knowledge attempt=1/2 retry_in=1s
   tool_timeout name=search_knowledge attempt=1/2 retry_in=1s
   plan step=1 decision=tool_call tool=search_knowledge
   Step 1: calling tool search_knowledge
   tool_timeout name=search_knowledge attempt=1/2 retry_in=1s
   plan step=2 decision=final_answer tool=None
   _stream_final_answer → direct LLM stream (no primary result)
   ```
   三个关键问题：
   - Plan LLM 第一步就并行调用 **两个** **`search_knowledge`**（相同工具、相同 query）
   - `search_knowledge` 15s 超时频繁触发 → 每次都重试 → 延迟翻倍
   - `final_answer` 前没有 `generate_answer` → 直接 LLM 流无 RAG 上下文
2. **分析** **`search_knowledge`** **超时链路**：
   ```
   search_knowledge (15s timeout)
     ├─ rewrite_query → LLM call (deepseek-chat) → 3-8s (第二轮有 history 更长)
     ├─ hybrid_search → ES BM25 + KNN → ~0.1s
     ├─ rerank → CrossEncoder (CPU) → ~1-2s
     └─ permission_check → ~0.01s
   ```
   rewrite\_query 的 LLM 调用是最大瓶颈，占总耗时 60-80%，第二轮因 history 加长更慢。
3. **检查 Plan prompt**：
   ```
   允许并行: search_knowledge + search_knowledge (不同query)
   复合问题优先并行检索：用 tools 数组同时调多个 search_knowledge。
   ```
   Prompt 明确鼓励 LLM 并行调用多次 search\_knowledge，但 LLM 用**相同 args** 调用两次，完全浪费。
4. **检查 FallbackPlanner 默认序列**：
   ```python
   {"type": "tool_call", "tool": "search_knowledge"},
   {"type": "final_answer"},                    # ← 缺少 generate_answer!
   ```
   硬编码路径也缺 `generate_answer`。
5. **检查** **`_stream_final_answer`** **无 primary result 时的行为**：

   当 `generate_answer` 没有被调用时，执行 "direct LLM stream"，只传 `ctx.messages` 不含 chunks → LLM 无资料 → "无法确定"。

### 根因

五个因素叠加：

| 因素                                 | 影响                                  |
| ---------------------------------- | ----------------------------------- |
| `search_knowledge` timeout 15s 太短  | rewrite LLM 3-8s + 其他 → 频繁触发超时+重试   |
| rewrite\_query 无独立超时               | 慢 LLM 响应阻塞整个 search\_knowledge      |
| Plan prompt 鼓励并行调用同一工具             | Step 0 双路搜索 → 双倍超时概率                |
| Plan LLM 跳过 generate\_answer       | final\_answer 时 chunks 未被处理为 prompt |
| `_stream_final_answer` 无 chunks 兜底 | 直接 LLM 流无 RAG 上下文 → 兜底回答            |

### 修复

| 文件                                                                   | 改动                                                                 |
| -------------------------------------------------------------------- | ------------------------------------------------------------------ |
| [`search_knowledge.py`](backend/app/tools/search_knowledge.py)       | `timeout=15.0` → `30.0`                                            |
| [`rewrite_query.py`](backend/app/tools/rewrite_query.py)             | LLM 调用加 `asyncio.wait_for(..., timeout=5.0)`，超时自动降级                |
| [`deepseek_provider.py`](backend/app/providers/deepseek_provider.py) | Plan prompt 重写：移除并行建议、强制 `search → generate → final` 三步流、禁止跳过      |
| [`agent_loop.py:325`](backend/app/harness/agent_loop.py)             | `final_answer` 前自动检查并注入 `generate_answer`                          |
| [`agent_loop.py:629`](backend/app/harness/agent_loop.py)             | `_stream_final_answer` 无 primary result 时用 search chunks 拼接 prompt |
| [`agent_loop.py:878`](backend/app/harness/agent_loop.py)             | FallbackPlanner 默认序列补充 `generate_answer`                           |

### 修复后效果

- 首 Token 延迟：5-10s → 预计 2-4s（消除重复搜索+超时重试）
- 第二轮对话：不再超时、不再跳过 generate\_answer、不再"无法确定"
- rewrite\_query 超 5s 自动降级为原始 query，不阻塞检索管线

***

## 5. 会话数据刷新后全部丢失 (2026-05-10)

> **一句话**：前端 Zustand 全内存存储未持久化 + 后端 session ID 读写前缀不一致（prefixed vs original），刷新后对话与历史全部消失。
> **修复**：前端 sessions/messages 持久化到 localStorage，后端读写统一用原始 session ID。

### 问题表现

刷新页面后，"对话"和"历史"两个栏目下的对话消息全部消失。`GET /api/v1/qa/sessions/{id}` 返回空数组。

### 根因

**前端**：Zustand store 全内存存储，`sessions` 和 `messages` 未持久化，刷新即归零。

**后端**：session 存储时用 `prefixed_session_id`（如 `kqa_abc123`），但 `GET /api/v1/qa/sessions/{id}` 查询时用前端传来的原始 ID（`abc123`），读写 ID 不匹配 → 永远找不到。

### 修复

| 文件                                                   | 改动                                                                                                       |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| [`chatStore.ts`](frontend/src/stores/chatStore.ts)   | sessions 持久化到 `localStorage "qa_sessions"`；messages 按 session 持久化到 `"qa_msgs_{sessionId}"`；切换/新建/删除时自动读写 |
| [`agent_loop.py`](backend/app/harness/agent_loop.py) | `prefixed_session_id` → `store_session_id = session_id`，读写统一用原始 ID                                       |

### 连带修复

- JWT Access Token TTL 从 900s (15min) → 28800s (8h)，避免使用期间 token 过期
- 来源详情空白：`hybrid_search.py` `_source` 列表补充 `chunk_id` 字段
- AI 回答非 Markdown 渲染：引入 `react-markdown`，新增 `MarkdownContent` 组件

***

## 6. Plan LLM 返回非 JSON + logger.exception() 崩溃 → \[50000] 网络连接中断 (2026-05-10)

> **一句话**：Plan LLM 输出自然语言非 JSON → guard 注入 generate\_answer → `logger.exception()` kwargs 不兼容致异常处理器自身崩溃 → SSE 连接断开返回 50000。
> **修复**：`logger.exception` 格式修正，`parse_plan_response` 增加正则提取 JSON，代码层去重并行调用。

### 问题表现

检索过程中直接返回报错：`[50000] 网络连接中断，请稍后重试`。

### 排查过程

<br />

1. **查看错误日志**：
   ```
   Plan step 2 failed: LLM 返回非 JSON 内容 (前100字符): 好的，我来分析一下当前的情况。
   根据对话历史和已完成的工具调用历史，用户的问题经历了三次变化...

   final_answer triggered before generate_answer — injecting generate_answer

   TypeError: Logger._log() got an unexpected keyword argument 'trace_id'
   ```
   三条关键线索：
   - Plan LLM 输出了自然语言解释而非 JSON → FallbackPlanner 接管
   - 我们的 guard 代码检测到 `generate_answer` 未执行，尝试注入
   - `logger.exception()` 本身崩溃（`trace_id` 不是标准 logging 的参数）
2. **崩溃链路**：
   ```
   Plan LLM 返回非 JSON → ValueError
     → _default_plan → final_answer
     → guard: inject generate_answer via _execute_tools
     → generate_answer 执行中抛异常 (ExceptionGroup)
     → except Exception → logger.exception("QA stream error", trace_id=..., session_id=...)
     → TypeError: Logger._log() got an unexpected keyword argument 'trace_id'
     → 异常处理本身崩溃 → SSE 连接断开 → 前端收到 50000
   ```
3. **Plan LLM 仍然并行调用 search\_knowledge**：
   ```
   Step 0: parallel calling 2 tools: ['search_knowledge', 'search_knowledge']
   Step 1: calling tool search_knowledge
   ```
   尽管改了 Prompt，deepseek-chat 仍然自行决定并行调用同一工具。

### 根因

**A. Plan LLM 非 JSON 输出**：`deepseek-chat` 在 plan 阶段忽略了 JSON 输出格式要求，输出了冗长的自然语言推理。`_parse_plan_response` 只尝试直接 JSON 解析，没有从自然语言中提取 JSON 的能力。

**B.** **`logger.exception()`** **kwargs 不兼容**：`qa.py:159` 使用了 `logger.exception("QA stream error", trace_id=..., session_id=...)`，但标准 `logging.Logger.exception()` 不接受额外 kwargs（这是 structlog 的用法），导致异常处理器自身崩溃。

**C. 并行重复调用无程序化拦截**：Prompt 层面的禁止并行对 deepseek-chat 无效，缺少代码层面的去重机制。

### 修复

| 文件                                                                       | 改动                                                                                                                                                          |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`qa.py:159`](backend/app/api/v1/qa.py#L159)                             | `logger.exception("QA stream error", trace_id=..., session_id=...)` → `logger.exception("QA stream error trace_id=%s session_id=%s", trace_id, session_id)` |
| [`deepseek_provider.py:128`](backend/app/providers/deepseek_provider.py) | `_parse_plan_response` 升级：JSON 直接解析失败 → 用正则从自然语言中提取 `{"type":"..."}`                                                                                        |
| [`agent_loop.py:467`](backend/app/harness/agent_loop.py)                 | 并行工具调用去重：相同 tool + 相同 args → 自动合并为 1 个                                                                                                                      |

### 防御措施

- **P0**：`qa.py` 异常处理应使用结构化日志或 `extra=` 字典，避免 kwargs 不兼容
- **P1**：Plan prompt 应进一步强化 JSON-only 约束（如 `你的回答必须是纯JSON，不要输出任何解释文字`）
- **P1**：Plan `temperature` 从 0.1 降到 0，最大化输出确定性

***

## 7. guard 代码连续两次参数错误导致 \[50000] 系统内部异常 (2026-05-10)

> **一句话**：BadCase #4/#6 仓促添加的 guard 代码连续两次调用 API 参数错误，且 Plan LLM 在 3 个 step 中死循环调 search\_knowledge 永不推进到 generate\_answer。
> **修复**：`_execute_tools` 补齐 6 个参数，`ctx.append_tool_result` 补齐双参数，Plan 前从 tools\_schema 移除已成功工具程序化强制推进。

### 问题表现

BadCase #6 修复后仍然报 `[50000] 抱歉，系统暂时无法处理您的问题，请稍后重试或联系管理员`。

### 排查过程

**第一轮修复后（BadCase #6）的日志**：

```
plan step=0 decision=tool_call tool=search_knowledge
plan step=1 decision=tool_call tool=search_knowledge
plan step=2 decision=tool_call tool=search_knowledge
final_answer triggered before generate_answer — injecting generate_answer
TypeError: _execute_tools() missing 2 required positional arguments: 'agent_config' and 'ctx'
```

**第二轮修复后的日志**：

```
plan step=0 decision=tool_call tool=search_knowledge
plan step=1 decision=tool_call tool=search_knowledge
plan step=2 decision=tool_call tool=search_knowledge
final_answer triggered before generate_answer — injecting generate_answer
TypeError: Context.append_tool_result() missing 1 required positional argument: 'result'
```

三次重复出现了同一种错误但每次参数错误不同：

| 修复轮次     | 错误                                                  | 原因                                                         |
| -------- | --------------------------------------------------- | ---------------------------------------------------------- |
| 原始 guard | `_execute_tools() missing 'agent_config' and 'ctx'` | 调用时只传了 3 个参数，签名需要 6 个                                      |
| 第一次修复    | `Context.append_tool_result() missing 'result'`     | `ctx.append_tool_result(result)` 签名为 `(tool_name, result)` |
| 根本原因     | Plan LLM 连续 3 步调用 search\_knowledge                 | Plan prompt 对 deepseek-chat 无效                             |

### 根因

**A. guard 代码未经过测试**：在 BadCase #4 中匆忙添加的 `final_answer` guard（注入 generate\_answer），两次调用 API 参数都不对：

```python
# 错误 v1: _execute_tools 参数不匹配
gen_result = await _execute_tools(
    [ToolCall(...)], tool_handlers, store_session_id, degrade,
)

# 错误 v2: append_tool_result 参数不匹配  
ctx.append_tool_result(result)
# 正确: ctx.append_tool_result(name, result)
```

**B. Plan LLM 死循环调用 search\_knowledge**：Prompt 层面禁止并行/重复对 deepseek-chat 完全无效。Plan LLM 在 3 个 step 中连续调用 search\_knowledge，从不推进到 generate\_answer。最终 max\_steps 耗尽触发 final\_answer → guard 注入 generate\_answer → 崩溃。

### 最终修复（三层防护）

|  层  | 位置                                                           | 改动                                                                                                      | 作用                            |
| :-: | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- | ----------------------------- |
|  1  | [agent\_loop.py](backend/app/harness/agent_loop.py) guard 调用 | `_execute_tools()` 正确传入 `decision=tool_handlers=user_claims=provider_router=agent_config=ctx=` 全部 6 个参数 | 修崩溃                           |
|  2  | [agent\_loop.py](backend/app/harness/agent_loop.py) guard 内部 | `ctx.append_tool_result(name, result)`                                                                  | 修崩溃                           |
|  3  | [agent\_loop.py](backend/app/harness/agent_loop.py) Plan 前拦截 | **search\_knowledge 成功后从 tools\_schema 移除；generate\_answer 成功后同样移除**                                    | 程序化强制推进 search→generate→final |

第三层是根本方案：不再依赖 LLM 理解 Prompt，而是在代码层面控制工具可见性。搜索成功后 Plan LLM 只能看到 `generate_answer`；生成成功后只能输出 `final_answer`。

### 防御措施

- **P0**：对 agent\_loop 中的关键路径（guard、Plan、execute）增加单元测试，覆盖异常分支
- **P0**：Plan `temperature` 从 0.1 降到 0，降低 LLM 输出自然语言的概率
- **P1**：Plan prompt 首句增加 `你的回答必须是纯JSON，不能包含任何解释文字`

***

## 8. LLM 答案生成幻觉：看似合理的高可信度编造 (2026-05-13)

> **一句话**：LLM 在生成答案时将不相关片段拼凑成"看似合理"的虚假信息，引用标注 [S1][S2] 格式规范但语义漂移，citation_verifier embedding 相似度未有效拦截，用户难以察觉。
> **修复**：Prompt 增加负面示例 + `needs_recheck` 机制，citation_verifier 引入 CrossEncoder 精排校验，幻觉检测前置到 streaming 前。

### 问题表现

用户提问"去年 KA 客户的年度合同金额最高是多少？"，系统返回：

> 根据参考文档，去年 KA 客户的年度合同金额最高为 **3,200 万元** [S1]，该合同签订于 2025 年 3 月 [S2]，客户为某大型制造企业 [S3]。

看似格式规范、引用完整。但实际：
- [S1] 片段原文是："普通客户年合同金额上限不超过 3,200 万元"（讲的是上限，而非实际最高值）
- [S2] 片段原文是："2025 年 3 月发布了新版合同管理规范"（讲的是规范发布时间，不是合同签订时间）
- [S3] 片段原文是："大型制造企业属于 L2 级别客户分类"（讲的是客户分类标准，不是合同主体）

**LLM 将三个不相关片段的信息抽取、拼接、改写，生成了看似合理但完全虚假的答案。**

### 排查过程

1. **检查 citation_verifier 报告**：
   ```json
   {
     "verified": [
       {"anchor": "S1", "similarity": 0.62, "status": "suspicious"},
       {"anchor": "S2", "similarity": 0.58, "status": "suspicious"},
       {"anchor": "S3", "similarity": 0.55, "status": "suspicious"}
     ],
     "overall_score": 0.58
   }
   ```
   三个引用全部处于 `suspicious` 区间 (0.55-0.75)，但没有一个低于 `CITATION_SUSPICIOUS=0.55` 触发 `mismatched`。**bi-encoder 余弦相似度对语义漂移不够敏感**——"上限不超过 3,200 万"和"最高为 3,200 万"的 embedding 向量距离很近，但语义含义完全不同。

2. **检查 hallucination_check 结果**：
   ```json
   {
     "score": 0.72,
     "verdict": "medium",
     "analysis": [
       {"sentence": "KA 客户的年度合同金额最高为 3,200 万元", "supported": true, "source": "S1"},
       {"sentence": "合同签订于 2025 年 3 月", "supported": true, "source": "S2"}
     ]
   }
   ```
   hallucination_check（LLM-as-judge）也判定为"有依据"——因为 LLM 自身同样存在语义漂移偏差，对"上限"→"最高值"、"发布时间"→"签订时间"这类细微篡改不够敏感。

3. **检查原始 chunks 内容**：三个片段均不包含"KA 客户合同最高金额"的答案，合理的 behavior 应该是"知识库中未找到该信息"的兜底回答。

### 根因

**四个维度的问题叠加导致幻觉穿透全部防线：**

#### 维度一：Context 治理 — 检索结果的相关性假阳性

`hybrid_search` 返回的 chunks 在关键词层面匹配了"合同金额""3,200 万""3 月""客户"等词，但**语义层面均不直接回答用户问题**。chunks 的 `rerank_score` 分散在 0.3-0.5 区间，而 [generate_answer.py:32](file:///c:/Q/Projects/QAny/backend/app/tools/generate_answer.py#L32) 的 `MIN_SCORE_THRESHOLD=0.4` 仅要求"不全低于 0.4"——没有一个 chunk 真正包含答案，但也没有触发全局降级。

**缺失**：没有 per-chunk "回答覆盖率"评估。当所有 chunk 都无法覆盖问题的核心意图时，应直接降级为兜底。

#### 维度二：Prompt — 缺少反面示例和精准度约束

[generate_answer.md](file:///c:/Q/Projects/QAny/backend/app/prompts/generate_answer.md) 的约束主要是方向性要求：
- ✓ "必须严格基于参考文档"
- ✓ "不得编造信息"
- ✗ **没有负面示例（Few-shot 反面案例）**：没有告诉 LLM 什么算"编造"——"上限不超过 X"≠"最高为 X"，这种细微语义篡改 LLM 自身也难以区分
- ✗ **没有数字/日期精确度要求**：没有"数字必须原样引用，不得修改、四舍五入或重述"的约束
- ✗ **没有"不确定就说不确定"的强化**：当信息存在歧义时应声明不确定性

#### 维度三：Citation 高亮引用 — 程序化校验粒度太粗

[citation_verifier.py](file:///c:/Q/Projects/QAny/backend/app/tools/citation_verifier.py) 有三层缺陷：

| 缺陷 | 代码位置 | 说明 |
|------|---------|------|
| **bi-encoder 余弦相似度对语义篡改不敏感** | [L81-85](file:///c:/Q/Projects/QAny/backend/app/tools/citation_verifier.py#L81-L85) | "上限 3,200 万" vs "最高 3,200 万" embedding 距离近但语义相反 |
| **阈值 `0.75/0.55` 一刀切** | [L15-16](file:///c:/Q/Projects/QAny/backend/app/tools/citation_verifier.py#L15-L16) | 没有根据 chunk 内容类型（数字/日期/名称）动态调整敏感度 |
| **orphan_claim 检测的 regex 太粗糙** | [L180-188](file:///c:/Q/Projects/QAny/backend/app/tools/citation_verifier.py#L180-L188) | `_is_filler()` 仅过滤礼貌用语和连接词，实际有引用的句子仍可能包含额外编造 |
| **引用覆盖不验证"额外编造"** | [L68-73](file:///c:/Q/Projects/QAny/backend/app/tools/citation_verifier.py#L68-L73) | 只验证有 `[Sx]` 的句子与 chunk 的相似度，不验证句子中未标注的额外信息是否也在 chunk 中 |

#### 维度四：架构时序 — 幻觉检测在 Streaming 之后，用户先看到错误答案

[agent_loop.py:376-433](file:///c:/Q/Projects/QAny/backend/app/harness/agent_loop.py#L376-L433) 的执行顺序：

```
stream_answer (LLM 流式输出) → 用户已看到全文
  → citation_verifier (程序化)     → 用户看到"正在验证引用可信度..."
    → hallucination_check (LLM)   → 用户看到"正在验证答案可信度..."
      → score < 0.6 → 替换为兜底  → 用户：刚才的答案呢？？
```

**核心矛盾**：幻觉检测是全链路中最重的环节（需要额外一次 LLM 调用），但被放在 streaming 之后。这导致：
- ✅ 不阻塞首 Token 延迟
- ❌ 用户先看到可能错误的答案，再被收回 → 严重 UX 问题
- ❌ 如果 hallucination_check 本身也犯错（本案例 score=0.72 判为 medium），错误答案直接送达用户

### 修复

#### 短期（Prompt 层面，立即生效）

**`generate_answer.md` 追加：**

```markdown
## 严禁行为（反面示例）
- ❌ 原文："金额上限不超过 3,200 万元" → 你写："金额最高为 3,200 万元"（篡改含义）
- ❌ 原文："2025 年 3 月发布规范" → 你写："合同签订于 2025 年 3 月"（张冠李戴）
- ❌ 原文："L2 级别客户分类包含大型制造企业" → 你写："客户为大型制造企业"（过度推断）

## 数字与日期规则
- 数字必须原样引用，不得换算、四舍五入、改写为近似值
- 日期必须保留原文语境（如"发布于"不可改为"签订于""成立于"）
- 信息存在歧义时，必须说明不确定并建议查阅原文
```

#### 中期（Citation 程序化层面）

| 改动 | 位置 | 说明 |
|------|------|------|
| `verify_citations()` 引入 CrossEncoder 精排 | [citation_verifier.py](file:///c:/Q/Projects/QAny/backend/app/tools/citation_verifier.py) | 对 `suspicious` 区间 (0.55-0.75) 的引用，用 CrossEncoder (query=sentence, doc=chunk) 做二次精判，CrossEncoder 对语义篡改更敏感 |
| 阈值分级：数字/日期类引用降低通过阈值 | [citation_verifier.py:L15-16](file:///c:/Q/Projects/QAny/backend/app/tools/citation_verifier.py#L15-L16) | 当 `_classify_claim()` 返回"数字"或"日期"时，`CITATION_VERIFIED` 从 0.75 提升到 0.85 |
| 新增"未标注额外事实"检测 | [citation_verifier.py](file:///c:/Q/Projects/QAny/backend/app/tools/citation_verifier.py) | 对有引用的句子，进一步拆解其非引用部分，检查是否引入了 Chunk 之外的额外事实 |

#### 长期（架构层面）

| 改动 | 说明 |
|------|------|
| **幻觉检测前移**：在 `_stream_final_answer` 前先跑一次快速的 citation 预检 | 如果 citation_report.overall_score < 0.5，跳过 LLM streaming，直接返回兜底——"知识库信息不足以回答该问题" |
| **hallucination_check 引入 Self-Consistency**：对同一答案用不同 temperature 调用 3 次 | 如果 3 次判定分歧大（如 2 次 low + 1 次 high），说明答案本身存在歧义，降低为兜底 |
| **`generate_answer` 增加 `needs_recheck` 机制** | 当 `rerank_score` 全部在 0.3-0.5 区间且无 chunk 明确覆盖问题核心时，标记 `needs_recheck: True`，跳过 LLM 直接兜底 |

### 防御措施

- **P0**：`generate_answer.md` 增加反面示例和数字/日期精确度要求
- **P0**：`generate_answer.py` 增加 `MIN_COVERAGE_SCORE=0.45`——当所有 chunk 的 rerank_score < 0.45 时直接兜底（不再仅判定"不全低于 0.4"）
- **P1**：`citation_verifier.py` 对 `suspicious` 引用引入 CrossEncoder 二次精排
- **P1**：`citation_verifier.py` 数字/日期类引用提高 `CITATION_VERIFIED` 阈值到 0.85
- **P1**：`agent_loop.py` 在 streaming 前跑 citation 预检，overall_score < 0.5 则直接兜底不流式输出
- **P2**：`hallucination_check` 引入 Self-Consistency (3 次调用投票)，降低 LLM-as-judge 的自身偏差
- **P2**：用户反馈机制：当答案被 replaced/downgraded 时，在 Event DONE 中附带 `downgrade_reason`，前端展示"本回答可信度不足，已自动隐藏"的提示

