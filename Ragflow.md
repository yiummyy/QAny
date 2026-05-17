---
tags: [RAG, AI, 工作流, 配置]
created: 2026-04-21
updated: 2026-04-22
cssclass: wide-tables
---

# RAGflow 项目配置与架构

本文档详细记录了RAGflow项目的模型配置方案、工具使用说明以及完整的工作流程。

## 目录
- [[#模型配置方案|模型配置方案]]
- [[#治理策略|治理策略]]
- [[#工具使用（TOOL USE）|工具使用（TOOL USE）]]
- [[#RAG详细工作流程|RAG详细工作流程]]
- [[#相关资源|相关资源]]

> **提示**：为了获得更好的阅读体验，建议在Obsidian设置中调整"可读线长度"为较宽的值（如1200px），或使用"切换可读线长度"命令。

## 模型配置方案


### 2. 中预算

| 环节                 | 推荐模型             | 国产/低成本替代          | 建议         |
| ------------------ | ---------------- | ----------------- | ---------- |
| 关键词生成              | GPT-5.4 nano     | deepseek-chat     | 没必要上强模型    |
| 跨语言扩展              | Gemini 2.5 Flash | Qwen3-14B         | 速度和质量平衡好   |
| 问题补全               | GPT-5.4 mini     | deepseek-chat     | 很适合做主力     |
| 候选问题生成             | GPT-5.4 mini     | Qwen3-30B-A3B     | 中档最划算      |
| 标签生成               | Claude Sonnet 4  | Qwen3-30B-A3B     | 分类边界更稳     |
| metadata 抽取        | GPT-5.4          | deepseek-reasoner | 这里建议开始上强模型 |
| TOC 生成             | Gemini 2.5 Pro   | Qwen3-235B-A22B   | 长文档场景更稳    |
| metadata filter 生成 | GPT-5.4          | deepseek-reasoner | 高价值环节      |
| 最终答案生成             | GPT-5.4          | Claude Sonnet 4   | 主回答位首选     |
| GraphRAG 抽取/消歧     | Claude Sonnet 4  | deepseek-reasoner | 强语义区分很重要   |
| 深度检索规划             | GPT-5.4          | deepseek-reasoner | 推理与规划都够强   |

- 适合：正式上线、效果和成本平衡
- 这是我最推荐的档位

### 3. 高预算

| 环节 | 推荐模型 | 国产高配替代 | 建议 |
|------|----------|--------------|------|
| 关键词生成 | GPT-5.4 nano | Qwen3-8B | 依然不用浪费强模型 |
| 跨语言扩展 | Gemini 2.5 Flash | Qwen-MT / Qwen3-14B | 高预算也不必堆大模型 |
| 问题补全 | GPT-5.4 mini | Qwen3-30B-A3B | 够用了 |
| 候选问题生成 | Claude Sonnet 4 | Qwen3-235B-A22B | 需要更自然的问题抽象 |
| 标签生成 | Claude Sonnet 4 | Qwen3-235B-A22B | 模糊分类更稳 |
| metadata 抽取 | GPT-5.4 | Qwen3-235B-A22B | 结构化输出优先 |
| TOC 生成 | Gemini 2.5 Pro | Qwen3-235B-A22B | 长上下文和层级理解最关键 |
| metadata filter 生成 | GPT-5.4 | deepseek-reasoner | 映射精度优先 |
| 最终答案生成 | GPT-5.4 | Claude Sonnet 4 / Gemini 2.5 Pro | 最强模型优先放这里 |
| GraphRAG 抽取/消歧 | Claude Sonnet 4 | Gemini 2.5 Pro / Qwen3-235B-A22B | 项目里最吃模型之一 |
| 深度检索规划 | GPT-5.4 | deepseek-reasoner | 多步推理能力优先 |

## 治理策略

![[../图片/Pasted image 20260420235215.png]]

![[../图片/Pasted image 20260421000316.png|601]]
![[../图片/Pasted image 20260421000343.png]]
![[../图片/Pasted image 20260421000401.png]]
![[../图片/Pasted image 20260421000422.png]]

## 工具使用（TOOL USE）
- 这里按 agent/tools/ 目录中的内置能力整理。
- 一共 22 个工具/能力项，其中 Tavily 拆成了 2 个工具：搜索与网页提取。
- 这批能力是项目里 Tool Use 的主要内置来源，目录见 [tools](file:///D:/%E5%A4%B8%E5%85%8B%E5%A4%87%E4%BB%BD/%E6%BA%90%E7%A0%81%E6%96%87%E4%BB%B6/ragflow-main/ragflow-main/agent/tools)。

**总表**

| 工具名                   | 组件名           | 主要用途                     | 典型场景               | 文件名              |
| --------------------- | ------------- | ------------------------ | ------------------ | ---------------- |
| search_my_dateset     | Retrieval     | 检索知识库/数据集内容              | 在私有知识库中查资料、找证据     | retrieval.py     |
| google_search         | Google        | Google Web 搜索            | 通用网页搜索、补充公开信息      | google.py        |
| duckduckgo_search     | DuckDuckGo    | DuckDuckGo 搜索            | 隐私友好搜索、一般网页/新闻查询   | duckduckgo.py    |
| searxng_search        | SearXNG       | 连接自建 SearXNG 元搜索         | 企业内自建搜索网关、可控搜索源    | searxng.py       |
| tavily_search         | TavilySearch  | 面向 AI 的联网搜索              | 实时资讯、网页摘要、联网问答     | tavily.py        |
| tavily_extract        | TavilyExtract | 提取指定 URL 正文              | 已知网页链接后抽正文、表格、文本   | tavily.py        |
| crawler               | Crawler       | 抓取网页并输出 HTML/Markdown/正文 | 深抓网页、把页面转成可读内容     | crawler.py       |
| wikipedia_search      | Wikipedia     | 查询 Wikipedia 条目          | 百科事实、概念解释、背景知识     | wikipedia.py     |
| github_search         | GitHub        | 搜索 GitHub 仓库             | 找开源项目、样例仓库、代码资产    | github.py        |
| arxiv_search          | ArXiv         | 搜索 arXiv 论文              | 查 CS/数学/AI 预印本论文   | arxiv.py         |
| google_scholar_search | GoogleScholar | 搜索学术文献                   | 学术综述、论文线索、引用追踪     | googlescholar.py |
| pubmed_search         | PubMed        | 搜索医学文献                   | 医学、生物、临床研究检索       | pubmed.py        |
| execute_sql           | ExeSQL        | 执行 SQL 查询                | 查业务库、做结构化数据分析      | exesql.py        |
| execute_code          | CodeExec      | 在沙箱中执行代码                 | 数据处理、可视化、复杂计算、生成文件 | code_exec.py     |
| email                 | Email         | 发送邮件                     | 给用户/同事发结果、带附件通知    | email.py         |
| yahoo_finance         | YahooFinance  | 获取股票/公司金融数据              | 看股价、公司信息、市场数据      | yahoofinance.py  |
| iwencai               | WenCai        | 同花顺问财选股/条件查询             | 中文股票筛选、条件选股        | wencai.py        |
| Jin10                 | Jin10         | 获取财经快讯/日历/行情符号           | 宏观快讯、财经事件、交易日历     | jin10.py         |
| TuShare               | TuShare       | 获取新闻/财经数据                | A 股资讯、财经新闻筛选       | tushare.py       |
| AkShare               | AkShare       | 获取财经/股票新闻数据              | 股票新闻、行情生态数据        | akshare.py       |
| QWeather              | QWeather      | 查询天气/指数/空气质量             | 城市天气、生活指数、空气质量     | qweather.py      |
| DeepL                 | DeepL         | 文本翻译                     | 多语言翻译、国际化内容转换      | deepl.py         |
## RAG详细工作流程
1. 文档上传
   ↓
2. 文档解析
   - 普通文本/PDF/HTML：规则解析、抽文本
   - 图片：OCR 或 VLM 描述
   - 视频：VLM 直接理解
   - 音频：语音转文本
   => 这里部分场景会用模型，但不全是文本 LLM

   ↓
3. 切块 / 分词 / 向量化
   - 切 chunk
   - 做 title/content tokenization
   - 生成 embedding 向量
   => 这里主要用 Embedding Model，不是聊天式 LLM

   ↓
4. 入库增强
   - 为每个 chunk 生成关键词
   - 为每个 chunk 生成候选问题
   - 为每个 chunk 抽取元数据
   - 为每个 chunk 打标签
   - 从正文自动生成 TOC
   => 这一层大量使用文本 LLM


   ↓
5. 用户提问
   ↓
6. 查询理解 / 改写
   - 多轮对话补全成完整问题
   - 跨语言扩展 query
   - 补充检索关键词
   - 自动生成 metadata filter
   => 这里使用文本 LLM

   ↓
7. 基础检索
   - 全文检索
   - 向量检索
   - 融合排序
   - 可选 rerank
   => embedding / rerank 会参与
   => 纯全文查询构造本身主要是规则，不是 LLM

   ↓
8. 可选增强链路 A：Deep Research
   - 先检索一轮
   - LLM 判断信息是否充足
   - 若不足，LLM 生成下一轮子问题和查询
   - 递归继续检索
   => 明确使用文本 LLM 做“检索规划”


   ↓
9. 可选增强链路 B：GraphRAG
   - 从 chunk 中抽实体/关系
   - 合并与摘要实体/关系描述
   - 实体消歧
   - 生成 community report
   - 检索时把问题改写为实体/类型关键词
   => 这里是 LLM 使用最重的一块之一

   ↓
10. 构造回答上下文
   - 组织 retrieved chunks
   - 注入 citation prompt
   - 拼接 knowledge prompt
   => 这里是 prompt 组装，不一定直接调用 LLM

   ↓
11. 最终答案生成
   - chat_model 根据系统提示词 + 检索结果 + 用户问题生成回答
   - 可流式输出
   => 这是标准 RAG 的最终生成环节
## 答案生成

### 1. 检索结果（Retrieval Results）的格式化
在大模型生成答案前，系统首先会通过向量数据库、全文检索或混合检索获取到相关的知识片段（Chunks），存放在变量 kbinfos["chunks"] 中。

随后，系统调用 rag/prompts/generator.py 中的 kb_prompt(kbinfos, max_tokens) 函数对检索结果进行组装：

- Token 控制 ：它会逐个计算 chunk 的 token 数量，确保拼接后的检索结果总长度不超过模型最大上下文窗口的 97% ，超出的部分会被直接丢弃。
- **元数据**拼接 ：将每个 chunk 的片段 ID、文档标题（Title）、文档 URL 等元数据与具体内容（Content）拼接成树状文本结构，以便 LLM 更好地理解上下文。
回到 dialog_service.py ，这些格式化后的知识片段会用分隔符拼接在一起，准备注入系统提示词：

```
kwargs["knowledge"] = "\n------\n" + "\n\n------\n\n".join
(knowledges)
```
### 2. 系统提示词（System Prompt）的构建
RAGFlow 的对话配置中包含一个系统提示词模板（prompt_config["system"] ），该模板内部通常会有一个 {knowledge} 占位符。

- 系统使用 Python 的字符串格式化，将上一步准备好的 kwargs["knowledge"] 注入到占位符中。
- 如果对话开启了“引用溯源”功能（quote=True），系统还会额外调用 citation_prompt() ，生成一段专门指导大模型如何标注引用的后缀提示词（例如要求模型在回答时加上 ##1 这样的标记）。
```
# 注入检索结果到系统提示词
msg = [{"role": "system", "content": prompt_config["system"].
format(**kwargs) + attachments_}]

# 追加引用规范提示词
prompt4citation = ""
if knowledges and (prompt_config.get("quote", True) and 
kwargs.get("quote", True)):
    prompt4citation = citation_prompt()
```
### 3. 用户问题与历史记录的处理
系统会将用户当前的问题以及近期的多轮对话历史加入到 msg 数组中。
为了防止对话历史过长导致 LLM 报错（Token 超限），代码会调用 message_fit_in 函数进行截断：
- 传入参数设定限制为大模型 max_tokens 的 95% 。
- 如果超过限制，算法会优先丢弃最早的对话历史，保留最新的“用户问题”和系统提示词。
```
msg.extend([{"role": m["role"], "content": re.sub(r"##\d
+\$\$", "", m["content"])} for m in messages if m["role"] != 
"system"])
# 确保总 Tokens 不超限
used_token_count, msg = message_fit_in(msg, int(max_tokens * 
0.95))
```
### 4. 调用大模型生成回答（Chat Model Invocation）
所有提示词准备完毕后，系统通过 LLMBundle （在 rag/llm/chat_model.py 中定义，底层封装了 litellm 或直接调用 openai API）正式发起请求。

系统将最终组装好的“**系统提示词 + 引用规范”和“对话历史 + 用户问题**”发送给 LLM（支持流式 stream 和非流式）：

```
if stream:
    # prompt + prompt4citation 是合并后的系统指令，msg[1:] 是用户
    和助手的对话轮次
    stream_iter = chat_mdl.async_chat_streamly_delta(prompt + 
    prompt4citation, msg[1:], gen_conf)
```
其中 gen_conf 包含了预设的生成参数，例如 temperature （温度）、 top_p 等。

### 5. 后处理与强制引用对齐（Decorate Answer）
大模型返回结果后，系统会在内部函数 decorate_answer 中对生成的文本进行后处理：

1. 思维链提取 ：如果使用的是 DeepSeek 这类推理模型，系统会切分并提取 <think>...</think> 标签中的推理过程。
2. 强制引用（Citation）回填 ：如果系统要求了引用（ quote=True ），但大模型比较“笨”，没有在生成的文本中输出 ##1$ 这样的引用标记，RAGFlow 会使用一种非常巧妙的兜底机制：
   - 提取生成的句子。
   - 调用 retriever.insert_citations ，利用 Embedding 模型 去计算生成句子与各个知识块（chunks）的向量相似度。
   - 强制将匹配度最高的知识块 ID 插入到句子末尾作为引用。
3. 统计耗时与 Token 消耗 ：计算检索阶段、LLM 生成阶段分别花了多少毫秒，以及每秒生成的 Token 速度，最终返回给前端展示。

## 记忆功能

### 1. 短期记忆：Json宽表记忆会话级别（Session-level）的历史上下文
#### message 字段 (JSON 数组)
用途：原封不动地存储对话的上下文流水，随时准备取出来传给大模型的 messages 参数。

```json
[
  {
    "id": "msg_000",
    "role": "assistant",
    "content": "你好！我是产品助手，请问有什么可以帮您？",
    "created_at": 1713780000
  },

```
#### reference 字段 (JSON 数组)
用途：存储 RAG 引擎在回答每个问题时，从向量数据库检索出来的知识库切片（Chunks）引文。前端用它来渲染“参考来源 [1][2]”。它的数组长度通常与 message 中大模型回答的次数对应。

```json
[
  {}, // 第一个 assistant 的问候语，没有参考引文
  {   // 对应第一轮问答的 RAG 检索结果
    "chunks": [
      {
        "chunk_id": "chk_abc",
        "content_with_weight": "本产品提供SaaS和私有化部署两种
        版本...",
        "doc_id": "doc_111",
        "doc_name": "产品白皮书.pdf",
        "similarity": 0.89
      }
    ],
    "doc_aggs": []
  },
```
### 2. 长期记忆
#### 跨会话持久化
长期记忆不绑定于某一次特定的聊天 Session，而是绑定于用户（User/Tenant）或特定的 Agent 角色。即使用户明天开启了一个新的对话，长期记忆依然能发挥作用。

#### 记忆的分类与提炼
在 Memory 表的 memory_type 字段中，RAGFlow 规划了高级记忆范式（通过位掩码区分）：

- **Semantic（语义记忆）**：提取的事实、概念或用户画像（比如“用户是一名程序员”、“用户偏好 Python”）。
- **Episodic（情景记忆）**：对过去发生的重要交互事件的总结。
- **Procedural（程序记忆）**：解决特定问题的固定流程或经验。

#### 不同的存储引擎
在 storage_type 字段中，长期记忆不仅仅使用关系型数据库的 Table，还可以引入 Graph（图数据库）或者 Vector DB（向量数据库）。当用户提问时，系统会先从长期记忆库中通过语义相似度检索出相关的“旧知识”，然后再放入当前对话的提示词中。

#### 元记忆表：主表（关系型配置表 MySQL/PostgreSQL）

| 字段名 (Column)      | 值 (Value)           | 说明                                                             |
| ----------------- | ------------------- | -------------------------------------------------------------- |
| id                | "mem_999abc"        | 记忆体的全局唯一ID。                                                    |
| name              | "User 001 Profile"  | 记忆体的名称。                                                        |
| tenant_id         | "tenant_888"        | 租户/用户 ID，保证数据隔离。                                               |
| memory_type       | 2                   | 位掩码。2 代表 semantic (语义记忆)。                                      |
| storage_type      | "table"             | 底层存储引擎，table指的是向量检索表 (比如Infinity/ES/OceanBase)。如果是 graph 则是图谱。 |
| embd_id           | "text-embedding-v2" | 绑定的 Embedding 模型 ID。它决定了记忆内容要用哪个模型转成向量。                        |
| llm_id            | "gpt-4o"            | 绑定的对话大模型，用于未来提炼或总结记忆。                                          |
| forgetting_policy | "FIFO"              | 遗忘策略，先进先出。                                                     |
| memory_size       | 5242880             | 记忆体的最大容量（字节）。超出就会按 FIFO 遗忘。                                    |

#### 内容载体表（向量数据库 Elasticsearch / Infinity / OceanBase）

| 字段名 (Field) | 值 (Value) | 字段类型 | 说明 |
|----------------|------------|----------|------|
| id | "msg_12345" | String | 这条具体记忆记录的 ID。 |
| memory_id | "mem_999abc" | String | 外键，关联到 MySQL 主表的配置。 |
| content_ltks | "我是一名后端开发工程师，我最常用的语言是 Python，不喜欢写前端" | Text | 原始文本，用于全文 BM25 关键词检索。 |
| tokenized_content_ltks | "我 是 一名 后端 开发..." | Text | 分词后的文本，方便底层引擎匹配。 |
| q_1024_vec | [-0.012, 0.055, 0.103, ..., 0.881] | Vector(1024) | 核心字段！1024 维的向量数据。用于语义检索。 |
| status_int | 1 | Integer | 状态（1=有效，0=被遗忘）。 |
| valid_at | 1713780000 | Timestamp | 记忆产生的时间。 |

### 它们是怎么配合工作的？（检索场景）
用户在对话里问大模型： “你能帮我写一个网页界面的脚本吗？”
1. 查主表 ：RAGFlow 知道当前用户关联了记忆体 mem_999abc 。
2. 转向量 ：系统把用户的新问题“你能帮我写一个网页界面的脚本吗？”用同样的 text-embedding-v2 转成查询向量（Query Vector）。
3. 向量检索 ：系统去向量数据库的 memory_mem_999abc 表里，执行 余弦相似度检索（KNN/ANN Search） 。
4. 命中记忆 ：因为“网页界面”和“前端”在语义上相近，底层数据库立刻算出了 q_1024_vec 的距离，把那条“我不喜欢写前端，我是Python后端”的记录召回。
5. 注入大模型 ：RAGFlow 在后台悄悄把这句记忆拼接到提示词里： 系统提示：已知用户偏好：“我是一名后端开发工程师，我最常用的语言是 Python，不喜欢写前端”。请回答用户的问题。
6. 最终回答 ：大模型机智地回复：“您好！既然您更偏好 Python 且不喜欢写前端，我们可以用 Streamlit 或 Gradio 这种 Python 库来快速生成网页界面，不需要您写 HTML/CSS。需要我给您一段代码吗？”

## 相关资源

- [[AI碎碎念/Agentic Workflow.md]] - 了解 Agentic 工作流与 RAGFlow 的关系
- [[工作经验/AI工具.md]] - 基于飞书CLI和AI工具的自动化实践经验
- [RAGFlow 官方文档](https://github.com/infiniflow/ragflow) - 项目源码与详细文档

```css
.wide-tables table {
  width: 100%;
  max-width: 100%;
}
.wide-tables {
  max-width: none;
}
```