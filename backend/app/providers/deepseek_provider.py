"""DeepSeek provider — fallback LLM via OpenAI-compatible REST API."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

from app.config import get_settings
from app.providers.base import BaseLLMProvider, ChatMessage, StreamChunk

logger = logging.getLogger(__name__)

DEEPSEEK_BASE = "https://api.deepseek.com/v1"


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek LLM provider as fallback. Model: deepseek-chat."""

    def __init__(self, model: str = "deepseek-chat", api_key: str | None = None) -> None:
        self.model = model
        if api_key is not None:
            self._api_key = api_key
        else:
            settings = get_settings()
            key = settings.deepseek_api_key
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
                f"{DEEPSEEK_BASE}/chat/completions", json=body, headers=headers
            )
            if resp.status_code != 200:
                raise RuntimeError(f"DeepSeek API error {resp.status_code}: {resp.text}")
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        if not content or not content.strip():
            raise RuntimeError("DeepSeek API 返回空 content")
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
            async with client.stream("POST", f"{DEEPSEEK_BASE}/chat/completions", json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"DeepSeek API error {resp.status_code}")
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
        "仅在以下情况允许并行（互不依赖，可同时调用）:\n",
        "  · search_knowledge + search_knowledge (不同 query 或不同 index，搜不同维度)\n",
        "  · search_knowledge + lookup_ticket (知识检索和工单查询互不依赖)\n",
        "  · search_knowledge + query_monitoring (知识检索和监控查询互不依赖)\n",
        "必须串行（依赖前一步结果，放到下一步）:\n",
        "  · search_knowledge → generate_answer (generate 依赖 search 的 chunks)\n",
        "  · search_knowledge → escalate (需评估检索结果)\n",
        "原则: 两个工具不共享输入输出依赖 → 并行。有依赖 → 串行分步。\n",
        '并行上限: 最多2个工具同时调用。\n',
        "\n## 🚫 并行调用红线（违反将导致调用被系统丢弃）\n",
        "严禁在并行 tools 数组中放入相同工具 + 相同参数的调用。\n",
        "  · 错误: tools=[search_knowledge(q='A'), search_knowledge(q='A')]  ← 完全重复，禁止\n",
        "  · 正确: tools=[search_knowledge(q='客户规则'), search_knowledge(q='去年政策')]  ← args 不同，允许\n",
        "  · 正确: tools=[search_knowledge(q='报修', index='ticket_knowledge'), search_knowledge(q='报修', index='qa_chunks')]  ← index 不同，允许\n",
        "\n## 标准流程（强制执行）\n",
        "Step 1: search_knowledge（检索知识库）\n",
        "  - 简单问题: 单个 search_knowledge 调用\n",
        "  - 复合问题（含多个独立子问题）或需跨知识库搜索: 用 tools 数组并行调用多个 search_knowledge（必须不同 query 或不同 index）\n",
        "Step 2: IF 检索充分 → generate_answer；ELSE → 换 query 重搜（最多重试1次）\n",
        "Step 3: final_answer\n",
        "\n## 决策规则（必须严格遵守）\n",
        "1. 首先：收到用户问题后，第一步必须是 search_knowledge 调用。单维度问题用一个 search_knowledge，多维度或跨知识库问题用 tools 数组并行（必须不同 args）。\n",
        "2. 然后：如果 search_knowledge 返回了 chunks，必须调用 generate_answer 处理结果。禁止跳过 generate_answer 直接 final_answer。\n",
        "3. 最后：generate_answer 成功后再输出 final_answer。\n",
        "4. raw_hit_count=0 或 rerank_top_score < 0.4 → 换 query 表述重搜1次 → 无论结果如何都继续 generate_answer → final_answer。\n",
        "5. 不要重复调用已执行成功的工具。\n",
        "6. 不推测：不要基于知识库外信息回答。\n",
        "7. 禁止绕过检索和生成：search_knowledge → generate_answer → final_answer 是强制路径。\n",
        "8. 跨知识库场景可并行：同一 query 搜不同知识库时传不同 index。同一 query 同一 index 只需单个调用，无需并行。\n",
    ]
    return "".join(parts)


def _parse_plan_response(response: str) -> dict[str, Any]:
    text = response.strip()
    if not text:
        raise ValueError("LLM 返回空响应，无法解析为 plan 决策")

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # LLM returned natural language with JSON embedded — try to extract it
    import re
    json_match = re.search(r'\{[^{}]*"type"\s*:\s*"(?:tool_call|final_answer)"[^{}]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"LLM 返回非 JSON 内容 (前100字符): {text[:100]}")
