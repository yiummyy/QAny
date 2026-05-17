import { useState, useEffect, useCallback } from "react";
import type { ConfirmationRequestData } from "../../types/qa";
import { confirmAction } from "../../api/qa";

interface Props {
  confirmation: ConfirmationRequestData;
  onChoice: (choice: "approved" | "rejected" | "timeout") => void;
}

type CardState = "pending" | "approved" | "rejected" | "timeout";

export default function ConfirmCard({ confirmation, onChoice }: Props) {
  const [state, setState] = useState<CardState>("pending");
  const [expanded, setExpanded] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  // Calculate remaining seconds
  const getRemaining = useCallback(() => {
    const expires = new Date(confirmation.expires_at).getTime();
    const now = Date.now();
    return Math.max(0, Math.floor((expires - now) / 1000));
  }, [confirmation.expires_at]);

  useEffect(() => {
    const remaining = getRemaining();
    setCountdown(remaining);

    if (remaining <= 0) {
      setState("timeout");
      onChoice("timeout");
      return;
    }

    const timer = setInterval(() => {
      const r = getRemaining();
      setCountdown(r);
      if (r <= 0) {
        setState("timeout");
        onChoice("timeout");
        clearInterval(timer);
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [getRemaining, onChoice]);

  const handleChoice = async (choice: "approved" | "rejected") => {
    if (state !== "pending" || submitting) return;
    setSubmitting(true);
    try {
      await confirmAction(confirmation.action_token, choice);
      setState(choice);
      onChoice(choice);
    } catch {
      // If the network call fails, still update UI optimistically
      setState(choice);
      onChoice(choice);
    } finally {
      setSubmitting(false);
    }
  };

  const iconMap: Record<string, string> = {
    create_ticket: "📋",
    escalate: "🔔",
    run_diagnostic: "🔧",
  };
  const icon = iconMap[confirmation.tool_name] ?? "⚡";

  if (state === "approved") {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-green-300 bg-green-50 px-4 py-3 my-2">
        <span className="text-lg">{icon}</span>
        <div>
          <p className="font-medium text-green-800">已确认：{confirmation.tool_label}</p>
          <p className="text-sm text-green-600">{confirmation.summary}</p>
        </div>
      </div>
    );
  }

  if (state === "rejected") {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 my-2 opacity-60">
        <span className="text-lg">{icon}</span>
        <div>
          <p className="font-medium text-gray-600">已取消：{confirmation.tool_label}</p>
          <p className="text-sm text-gray-500">{confirmation.summary}</p>
        </div>
      </div>
    );
  }

  if (state === "timeout") {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 my-2 opacity-60">
        <span className="text-lg">⏰</span>
        <div>
          <p className="font-medium text-gray-600">已超时自动取消：{confirmation.tool_label}</p>
          <p className="text-sm text-gray-500">{confirmation.summary}</p>
        </div>
      </div>
    );
  }

  // pending state
  const detailEntries = Object.entries(confirmation.details);
  const formatLabel = (key: string) => {
    const labelMap: Record<string, string> = {
      title: "标题",
      description: "描述",
      priority: "优先级",
      category: "分类",
      ticket_id: "工单编号",
      reason: "原因",
      device_name: "设备名称",
      check_type: "诊断类型",
    };
    return labelMap[key] ?? key;
  };
  const formatValue = (value: unknown) => {
    if (typeof value === "string") {
      // Truncate long descriptions
      return value.length > 200 ? value.slice(0, 200) + "…" : value;
    }
    return String(value);
  };

  return (
    <div className="rounded-lg border border-blue-300 bg-blue-50 px-4 py-3 my-2 shadow-sm">
      <div className="flex items-start gap-3">
        <span className="text-lg mt-0.5">{icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="font-medium text-blue-900">
              {confirmation.tool_label}
            </p>
            <span className="text-xs text-blue-500 whitespace-nowrap tabular-nums">
              {countdown}s
            </span>
          </div>
          <p className="text-sm text-blue-700 mt-1">{confirmation.summary}</p>

          {detailEntries.length > 0 && (
            <button
              type="button"
              onClick={() => setExpanded(!expanded)}
              className="text-xs text-blue-500 hover:text-blue-700 mt-2 underline"
            >
              {expanded ? "收起详情 ▲" : "查看详情 ▼"}
            </button>
          )}

          {expanded && (
            <div className="mt-2 rounded bg-white/60 p-2 text-xs space-y-1">
              {detailEntries.map(([key, value]) => (
                <div key={key} className="flex gap-2">
                  <span className="font-medium text-gray-500 shrink-0">
                    {formatLabel(key)}:
                  </span>
                  <span className="text-gray-700 break-all">
                    {formatValue(value)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex gap-2 mt-3 justify-end">
        <button
          type="button"
          disabled={submitting}
          onClick={() => handleChoice("rejected")}
          className="px-3 py-1.5 text-sm rounded border border-gray-300 bg-white text-gray-600 hover:bg-gray-100 disabled:opacity-50"
        >
          取消
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={() => handleChoice("approved")}
          className="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          确认
        </button>
      </div>
    </div>
  );
}
