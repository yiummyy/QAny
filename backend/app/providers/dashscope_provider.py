"""DashScope (Qwen) provider — Qwen-Plus / Qwen-Turbo via REST API."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

from app.config import get_settings
from app.providers.base import BaseLLMProvider, ChatMessage, StreamChunk

logger = logging.getLogger(__name__)

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class DashScopeProvider(BaseLLMProvider):
    """DashScope LLM provider. Default model: qwen-plus."""

    def __init__(self, model: str = "qwen-plus", api_key: str | None = None) -> None:
        self.model = model
        self.base_url = DASHSCOPE_BASE
        if api_key is not None:
            self._api_key = api_key
        else:
            settings = get_settings()
            key = settings.dashscope_api_key
            self._api_key = key.get_secret_value() if key else ""

    async def chat(self, messages: list[ChatMessage], **kwargs: Any) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 2000),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", json=body, headers=headers
            )
            if resp.status_code != 200:
                raise RuntimeError(f"API error {resp.status_code}: {resp.text}")
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        if not content or not content.strip():
            raise RuntimeError(f"API 返回空 content (model={self.model})")
        return content

    async def stream_chat(self, messages: list[ChatMessage], **kwargs: Any) -> AsyncIterator[StreamChunk | str]:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 2000),
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    body_snippet = ""
                    try:
                        body_snippet = await resp.aread()
                        body_snippet = body_snippet.decode("utf-8", errors="replace")[:500]
                    except Exception:
                        pass
                    raise RuntimeError(f"API error {resp.status_code}: {body_snippet}")
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            reasoning = delta.get("reasoning_content", "")
                            if reasoning or content:
                                yield {"content": content, "reasoning_content": reasoning}
                        except json.JSONDecodeError:
                            continue

    async def plan(self, messages: list[ChatMessage], tools_schema: list[dict[str, Any]]) -> dict[str, Any]:
        system_msg = _build_plan_system_prompt(tools_schema)
        full_messages: list[ChatMessage] = [{"role": "system", "content": system_msg}, *messages]
        response = await self.chat(full_messages, temperature=0.1, max_tokens=500)
        return _parse_plan_response(response)


def _build_plan_system_prompt(tools_schema: list[dict[str, Any]]) -> str:
    available_tools = [t["name"] for t in tools_schema if t.get("name")]
    tools_desc = json.dumps(tools_schema, ensure_ascii=False, indent=2)
    parts = [
        "你是一个Agent规划器。根据对话历史和用户问题，决定下一步操作。\n",
        "## 可用工具\n",
        tools_desc,
        "\n## 输出格式\n",
        '严格遵守JSON格式。单工具调用：\n',
        '{"type": "tool_call", "tool": "工具名称", "args": {"参数名": "参数值"}}\n',
        '多工具并行调用（仅限无依赖关系的工具）：\n',
        '{"type": "tool_call", "tools": [{"tool": "工具1", "args": {...}}, {"tool": "工具2", "args": {...}}], "reasoning": "并行原因"}\n',
        '或者 {"type": "final_answer"}\n',
        "\n## 并行工具调用规则\n",
        "你可以一次调用多个工具，但必须遵守依赖约束：\n",
        "允许并行（互不依赖，可同时调用）:\n",
        "  · search_knowledge + search_knowledge (不同 query 或不同 index，搜不同维度)\n",
        "  · search_knowledge + lookup_ticket (知识检索和工单查询互不依赖)\n",
        "  · search_knowledge + query_monitoring (知识检索和监控查询互不依赖)\n",
        "必须串行（依赖前一步结果，放到下一步）:\n",
        "  · search_knowledge → generate_answer (generate 依赖 search 的 chunks)\n",
        "  · search_knowledge → escalate (需评估检索结果)\n",
        "  · create_ticket → lookup_ticket (依赖创建的 ticket_id)\n",
        "原则: 两个工具不共享输入输出依赖 → 并行。有依赖 → 串行分步。\n",
        '并行上限: 最多3个工具同时调用。\n',
        "\n## 🚫 并行调用红线（违反将导致调用被系统丢弃）\n",
        "严禁在并行 tools 数组中放入相同工具 + 相同参数的调用。\n",
        "  · 错误示例: tools=[search_knowledge(q='A'), search_knowledge(q='A')]  ← 完全重复，禁止\n",
        "  · 正确示例: tools=[search_knowledge(q='客户规则'), search_knowledge(q='去年政策')]  ← args 不同，允许\n",
        "  · 正确示例: tools=[search_knowledge(q='报修流程', index='ticket_knowledge'), search_knowledge(q='报修流程', index='qa_chunks')]  ← index 不同，允许\n",
        "\n## 标准流程\n",
        "Step 1: search_knowledge（检索知识库，工具会自动选择合适知识库）\n",
        "Step 2: generate_answer（基于检索到的文档片段生成答案）\n",
        "Step 3: final_answer\n",
        "\n## 决策规则\n",
        "1. 【强制】必须先调用 search_knowledge，再调用 generate_answer，最后 final_answer。禁止跳过检索直接输出 final_answer。\n",
        "2. 评估 search_knowledge 返回的诊断信息（summary 中包含召回数、重排最高分）：\n",
        "   - raw_hit_count=0 → 换 query 表述重搜（最多1次，仅改 query 参数，无需传 index）\n",
        "   - rerank_top_score < 0.4 → 检索相关度不足，换 query 重搜或 final_answer 降级\n",
        "   - 检索充分 → generate_answer → final_answer\n",
        "3. search_knowledge 会自动根据实体和意图选择合适的知识库，通常无需指定 index 参数。仅当明确判断需要补搜特定知识库时才传 index 显式覆盖。\n",
        "4. 复合问题（含多个独立子问题）优先并行检索：如果问题可以拆成2-3个独立子问题，用 tools 数组同时调用多个 search_knowledge（必须不同 query 或不同 index），比串行重搜更高效。\n",
        "5. 跨知识库场景可并行：同一 query 搜不同知识库（如 ticket_knowledge + qa_chunks）时传不同 index，系统自动去重。\n",
        "6. 仅使用上面列出的可用工具。不得调用未列出的工具名。\n",
        "7. 不推测：必须基于知识库中的参考文档回答问题，不得使用自身训练数据。\n",
        "8. 不做多余步骤：不要重复调用已成功的同名工具（换参数重试最多1次）。严禁 tools 数组中出现完全相同的 (工具名 + 参数) 组合。\n",
    ]
    return "".join(parts)


def _parse_plan_response(response: str) -> dict[str, Any]:
    text = response.strip()
    if not text:
        raise ValueError("LLM 返回空响应，无法解析为 plan 决策")
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if not text:
            raise ValueError("LLM 返回空 markdown 代码块")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM 返回非 JSON 内容 (前100字符): {text[:100]}") from exc
