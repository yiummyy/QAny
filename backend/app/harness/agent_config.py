"""AgentConfig dataclass — per-agent configuration for the shared AgentLoop."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Resolve prompts directory relative to this file
_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def _load_plan_prompt(filename: str) -> str:
    """Load a plan system prompt from app/prompts/plan/<filename>.md."""
    path = _PROMPTS_DIR / "plan" / f"{filename}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


@dataclass
class AgentConfig:
    """Per-agent configuration — one instance per business scenario.

    The AgentLoop class is shared; AgentConfig provides the differentiation
    points (tools, prompts, knowledge index, etc.).
    """

    # --- Identity ---
    name: str = "KnowledgeQA"
    display_name: str = "知识库问答"

    # --- Knowledge ---
    es_index: str = "qa_chunks"
    available_indexes: list[str] = field(default_factory=lambda: ["qa_chunks"])
    rag_top_k_search: int = 20
    rag_top_k_rerank: int = 5
    rag_rerank_enabled: bool = True
    rag_rewrite_enabled: bool = True

    # --- Answer ---
    answer_template: str = "generate_answer"

    # --- Tools ---
    extra_tools: dict[str, Any] = field(default_factory=dict)

    # --- Fallback plan (when Plan LLM is unavailable) ---
    fallback_plan_sequence: list[dict[str, Any]] = field(default_factory=list)

    # --- Prompts ---
    plan_system_prompt: str = ""

    # --- Limits ---
    max_steps: int = 5

    # --- Session ---
    session_prefix: str = ""


AGENT_PRESETS: dict[str, AgentConfig] = {
    "KnowledgeQA": AgentConfig(
        name="KnowledgeQA",
        display_name="知识库问答",
        es_index="qa_chunks",
        available_indexes=["qa_chunks", "ticket_knowledge", "sales_knowledge", "ops_knowledge"],
        rag_top_k_search=20,
        rag_top_k_rerank=5,
        rag_rerank_enabled=True,
        rag_rewrite_enabled=True,
        answer_template="generate_answer",
        extra_tools={},
        max_steps=3,
        session_prefix="kqa_",
        fallback_plan_sequence=[
            {"type": "tool_call", "tool": "search_knowledge", "args": {"query": "{query}"}},
            {"type": "tool_call", "tool": "generate_answer", "args": {}},
            {"type": "final_answer"},
        ],
    ),
    "ServiceTicket": AgentConfig(
        name="ServiceTicket",
        display_name="服务工单",
        es_index="ticket_knowledge",
        available_indexes=["ticket_knowledge", "qa_chunks"],
        rag_top_k_search=20,
        rag_top_k_rerank=5,
        rag_rerank_enabled=True,
        rag_rewrite_enabled=True,
        answer_template="generate/service_ticket_answer",
        extra_tools={},
        plan_system_prompt=_load_plan_prompt("service_ticket"),
        max_steps=5,
        session_prefix="st_",
        fallback_plan_sequence=[
            {"type": "tool_call", "tool": "search_knowledge", "args": {"query": "{query}"}},
            {"type": "tool_call", "tool": "generate_answer", "args": {}},
            {"type": "tool_call", "tool": "create_ticket", "args": {
                "title": "用户咨询: {query}", "description": "Plan LLM 不可用时自动创建",
                "priority": "medium", "category": "其他",
            }},
            {"type": "final_answer"},
        ],
    ),
    "SalesContent": AgentConfig(
        name="SalesContent",
        display_name="营销内容",
        es_index="sales_knowledge",
        available_indexes=["sales_knowledge", "qa_chunks"],
        rag_top_k_search=20,
        rag_top_k_rerank=5,
        rag_rerank_enabled=True,
        rag_rewrite_enabled=True,
        extra_tools={},
        max_steps=5,
        session_prefix="sc_",
        fallback_plan_sequence=[
            {"type": "tool_call", "tool": "search_knowledge", "args": {"query": "{query}"}},
            {"type": "tool_call", "tool": "generate_answer", "args": {}},
            {"type": "final_answer"},
        ],
    ),
    "OpsSupport": AgentConfig(
        name="OpsSupport",
        display_name="运维支持",
        es_index="ops_knowledge",
        available_indexes=["ops_knowledge", "qa_chunks"],
        rag_top_k_search=20,
        rag_top_k_rerank=5,
        rag_rerank_enabled=True,
        rag_rewrite_enabled=True,
        extra_tools={},
        max_steps=5,
        session_prefix="ops_",
        fallback_plan_sequence=[
            {"type": "tool_call", "tool": "search_knowledge", "args": {"query": "{query}"}},
            {"type": "tool_call", "tool": "generate_answer", "args": {}},
            {"type": "final_answer"},
        ],
    ),
}

SCENE_TO_AGENT: dict[str, str] = {
    "general": "KnowledgeQA",
    "knowledge": "KnowledgeQA",
    "ticket": "ServiceTicket",
    "service": "ServiceTicket",
    "sales": "SalesContent",
    "ops": "OpsSupport",
}
