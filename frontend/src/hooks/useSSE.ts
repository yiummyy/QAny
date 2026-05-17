import { useRef, useCallback } from "react";
import { useAuthStore } from "../stores/authStore";
import type { ChatPhase, SourceItem, CitationReport, ConfirmationRequestData } from "../types/qa";

export interface SSEHandlers {
  onPhaseChange?: (phase: ChatPhase, message?: string) => void;
  onChunk?: (text: string, reasoningText?: string) => void;
  onDone?: (data: {
    answer: string;
    sources: SourceItem[];
    confidence: "high" | "medium" | "low";
    confidence_score: number;
    citations?: CitationReport | null;
    steps: number;
    trace_id: string;
    response_time_ms: number;
  }) => void;
  onError?: (code: number, message: string, fallbackAnswer?: string) => void;
  onConfirmRequired?: (data: ConfirmationRequestData) => void;
}

export function useSSE() {
  const abortRef = useRef<AbortController | null>(null);

  const connect = useCallback(
    async (question: string, sessionId: string, handlers: SSEHandlers, scene?: string) => {
      const token = useAuthStore.getState().accessToken;
      if (!token) throw new Error("未登录");

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const longWaitTimer = window.setTimeout(() => {
        handlers.onPhaseChange?.("long_wait", "系统处理中，请耐心等待");
      }, 10000);

      try {
        const response = await fetch("/api/v1/qa/ask", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ question, session_id: sessionId, scene }),
          signal: controller.signal,
        });

        if (!response.ok) {
          let code = response.status;
          let message = "请求失败";
          try {
            const errBody = await response.json();
            // Check for flattened error envelope first
            if (errBody.code !== undefined && errBody.message !== undefined) {
              code = errBody.code;
              message = errBody.message;
            } else if (errBody.detail) {
              // Fallback for older detail format
              code = errBody.detail.code ?? code;
              message = errBody.detail.message ?? message;
            }
          } catch {
            // use defaults
          }
          handlers.onError?.(code, message);
          return;
        }

        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let eventType = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            // Strip trailing \r for servers that use \r\n line endings
            const cleanLine = line.endsWith("\r") ? line.slice(0, -1) : line;
            if (cleanLine.startsWith("event: ")) {
              eventType = cleanLine.slice(7).trim();
            } else if (cleanLine.startsWith("data: ")) {
              const dataStr = cleanLine.slice(6);
              try {
                const data = JSON.parse(dataStr);
                switch (eventType) {
                  case "status":
                    clearTimeout(longWaitTimer);
                    handlers.onPhaseChange?.(
                      (data.phase as ChatPhase) ?? "thinking",
                      data.message,
                    );
                    // Handle confirmation request embedded in status event
                    if (
                      data.phase === "confirming" &&
                      data.confirmation
                    ) {
                      handlers.onConfirmRequired?.(data.confirmation);
                    }
                    break;
                  case "message":
                    clearTimeout(longWaitTimer);
                    handlers.onPhaseChange?.("streaming");
                    handlers.onChunk?.(data.chunk ?? "", data.reasoning_chunk ?? "");
                    break;
                  case "done":
                    clearTimeout(longWaitTimer);
                    handlers.onDone?.(data);
                    break;
                  case "error":
                    clearTimeout(longWaitTimer);
                    handlers.onError?.(
                      data.code,
                      data.message,
                      data.fallback_answer,
                    );
                    break;
                }
              } catch {
                // skip malformed SSE data
              }
              eventType = "";
            }
          }
        }
      } catch (err: unknown) {
        clearTimeout(longWaitTimer);
        if (
          err instanceof DOMException &&
          err.name === "AbortError"
        ) {
          return;
        }
        handlers.onError?.(50000, "网络连接中断，请稍后重试");
      }
    },
    [],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { connect, cancel };
}
