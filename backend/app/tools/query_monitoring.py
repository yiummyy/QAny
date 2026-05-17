"""Tool: query_monitoring — query device metrics (OpsSupport agent only, B9)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.auth.claims import UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import register_agent_tool


class QueryMonitoringInput(BaseModel):
    device_name: str = Field(..., description="设备名称，如 逆变器-3号")
    metric: str = Field(default="all", description="指标: cpu/mem/disk/temp/all")
    time_range: str = Field(default="1h", description="时间范围: 5m/15m/1h/6h/24h")


@register_agent_tool("OpsSupport", "query_monitoring", QueryMonitoringInput, timeout=15.0, max_retries=1)
async def query_monitoring(
    device_name: str,
    metric: str = "all",
    time_range: str = "1h",
    *,
    user_claims: UserClaims,
) -> ToolResult:
    """Query device monitoring metrics (MVP: mock)."""
    # MVP mock — returns placeholder metrics
    metrics = {
        "device": device_name,
        "time_range": time_range,
        "readings": {
            "cpu_percent": 67.3,
            "memory_percent": 72.1,
            "disk_percent": 45.8,
            "temperature_c": 42.5,
        },
        "alerts": [
            {"level": "warning", "message": f"{device_name} CPU 使用率偏高 (67.3%)", "time": "2026-04-30T14:00:00Z"},
        ],
        "status": "warning",
    }

    return ToolResult(
        status="ok",
        summary=f"监控查询: {device_name} CPU:{metrics['readings']['cpu_percent']}% MEM:{metrics['readings']['memory_percent']}%",
        data={"metrics": metrics},
    )
