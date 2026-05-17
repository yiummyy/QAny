"""Tool: run_diagnostic — run device diagnostic checks (OpsSupport agent only, B9)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.auth.claims import UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import register_agent_tool


class RunDiagnosticInput(BaseModel):
    device_name: str = Field(..., description="设备名称")
    check_type: str = Field(
        default="all",
        description="诊断类型: connectivity/logs/config/all",
    )


@register_agent_tool("OpsSupport", "run_diagnostic", RunDiagnosticInput,
                     timeout=30.0, max_retries=1,
                     requires_confirmation=True, confirmation_timeout=120.0)
async def run_diagnostic(
    device_name: str,
    check_type: str = "all",
    *,
    user_claims: UserClaims,
) -> ToolResult:
    """Run device diagnostic checks (MVP: mock)."""
    # MVP mock — returns placeholder diagnostic report
    report = {
        "device": device_name,
        "check_type": check_type,
        "timestamp": "2026-04-30T14:05:00Z",
        "results": [
            {"check": "connectivity", "status": "pass", "detail": "网络连通正常，延迟 2ms"},
            {"check": "logs", "status": "warn", "detail": "最近1小时内有 3 条 WARN 日志"},
            {"check": "config", "status": "pass", "detail": "配置文件校验通过"},
        ],
        "suggestions": [
            "检查 /var/log/app/error.log 中的 WARN 日志详情",
            "建议关注 CPU 使用率趋势，当前 67.3% 接近阈值",
        ],
        "overall": "warning",
    }

    return ToolResult(
        status="ok",
        summary=f"诊断完成: {device_name} ({check_type}) → {report['overall']}",
        data={"report": report},
    )
