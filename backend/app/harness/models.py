"""Harness 核心数据模型 — Event / ToolResult / Context / PlanDecision."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    STATUS = "status"
    MESSAGE = "message"
    DONE = "done"
    ERROR = "error"


class Event(BaseModel):
    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    status: str  # "ok" | "error" | "degraded" | "chitchat"
    summary: str  # short summary for LLM context compression
    data: Any | None = None  # full data for downstream tools / main loop


@dataclass
class ObservationBlock:
    """Structured observation extracted from a tool result for the Agent Observe phase.

    Programmatic quality assessment — no LLM involved.
    """

    step: int
    tool_name: str

    # ---- generic ----
    status: str = ""  # "ok" | "degraded" | "error" | "chitchat"
    should_stop: bool = False
    stop_reason: str = ""

    # ---- search_knowledge specific ----
    hit_count: int = 0
    top_score: float = 0.0
    coverage_verdict: str = ""  # "充足" | "一般" | "不足"
    indexes_searched: list[str] = field(default_factory=list)

    # ---- generate_answer specific ----
    answer_ready: bool = False
    quality_gate_passed: bool = False

    # ---- gap analysis ----
    gap_description: str = ""
    suggested_action: str = ""


class ToolHandler(BaseModel):
    name: str
    input_schema: type[BaseModel]  # pydantic schema for LLM function_call
    fn: Any  # async callable
    timeout: float = 30.0  # per-tool timeout in seconds
    max_retries: int = 0  # max retry attempts (0 = no retry)
    retryable_exceptions: Any = ()  # tuple of exception types eligible for retry
    requires_confirmation: bool = False  # whether user confirmation is required before execution
    confirmation_timeout: float = 120.0  # auto-reject timeout in seconds
    model_config = ConfigDict(arbitrary_types_allowed=True)


class ConfirmationRequest(BaseModel):
    """SSE confirm_required event payload — sent to frontend."""
    action_token: str
    tool_name: str
    tool_label: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    expires_at: str  # ISO 8601


class ConfirmationResponse(BaseModel):
    """Frontend POST /confirm request body."""
    action_token: str
    choice: str  # "approved" | "rejected"


class ToolCall(BaseModel):
    """A single tool invocation within a PlanDecision."""
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class PlanDecision(BaseModel):
    type: str  # "tool_call" | "final_answer"
    tool: str | None = None  # single tool (backward compat)
    args: dict[str, Any] | None = None  # args for single tool
    tools: list[ToolCall] | None = None  # multi-tool parallel execution (new)
    reasoning: str | None = None  # LLM decision rationale (observability)
    metadata: dict[str, Any] | None = None


@dataclass
class Context:
    system_prompt: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    _compacted_summary: str | None = None
    pinned_constraints: list[PinnedConstraint] = field(default_factory=list)
    constraint_step: int = 0
    observation_log: list[ObservationBlock] = field(default_factory=list)
    retry_count: int = 0

    def token_count(self) -> int:
        """Rough token estimate. Chinese ~1.5 char/token, English ~0.25 char/token."""
        total = 0
        for msg in self.messages:
            total += len(msg.get("content", ""))
        for tr in self.tool_results:
            total += len(tr.get("summary", ""))
        total += len(self.system_prompt)
        if self._compacted_summary:
            total += len(self._compacted_summary)
        return int(total * 0.3)

    def append_tool_result(self, tool_name: str, result: ToolResult) -> None:
        self.tool_results.append({
            "tool": tool_name,
            "summary": result.summary,
            "status": result.status,
            "data": result.data,
        })

    def pin_constraint(
        self, constraint: str, constraint_type: str,
        source_step: int = 0, expires_after_steps: int = 0,
    ) -> None:
        """Add a constraint that survives compaction."""
        self.pinned_constraints.append(PinnedConstraint(
            constraint=constraint, source_step=source_step or self.constraint_step,
            constraint_type=constraint_type, expires_after_steps=expires_after_steps,
        ))


@dataclass
class PinnedConstraint:
    """User-declared constraint that must survive context compaction."""
    constraint: str
    source_step: int
    constraint_type: str  # "region"|"time_range"|"product_line"|"department"|"other"
    expires_after_steps: int = 0  # 0 = never expires within session


# ---------------------------------------------------------------------------
# Citation verification models (Spec: citation-verification)
# ---------------------------------------------------------------------------


class VerifiedCitation(BaseModel):
    """A verified citation anchor in the answer."""
    anchor: str                       # "S1"
    sentence: str                     # original sentence containing the anchor
    chunk_id: str
    similarity: float                 # cosine similarity 0~1
    status: str                       # "verified" | "suspicious" | "mismatched"


class OrphanClaim(BaseModel):
    """A factual claim in the answer without a source citation."""
    sentence: str
    claim_type: str                   # "数字" | "日期" | "规定" | "名称" | "其他"


class CitationReport(BaseModel):
    """Full citation verification report."""
    verified: list[VerifiedCitation] = Field(default_factory=list)
    unverified: list[VerifiedCitation] = Field(default_factory=list)
    orphan_claims: list[OrphanClaim] = Field(default_factory=list)
    coverage: float = 0.0             # cited sentences / total claim sentences
    overall_score: float = 0.0        # composite trust score 0~1
