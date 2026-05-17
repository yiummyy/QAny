"""Base LLM Provider ABC — Spec §2.3."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, TypedDict


class ChatMessage(TypedDict, total=False):
    role: str
    content: str


class StreamChunk(TypedDict, total=False):
    content: str
    reasoning_content: str


class BaseLLMProvider(ABC):
    """Abstract interface for LLM providers. Three methods: chat / stream_chat / plan."""

    model: str

    @abstractmethod
    async def chat(self, messages: list[ChatMessage], **kwargs: Any) -> str:
        """Return complete response at once."""
        ...

    @abstractmethod
    async def stream_chat(self, messages: list[ChatMessage], **kwargs: Any) -> AsyncIterator[StreamChunk | str]:
        """Yield tokens one at a time."""
        ...

    @abstractmethod
    async def plan(self, messages: list[ChatMessage], tools_schema: list[dict[str, Any]]) -> dict[str, Any]:
        """Agent planning: return tool_call or final_answer decision as JSON."""
        ...
