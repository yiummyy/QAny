import { useState, useRef, useEffect } from "react";
import { useChatStore } from "../../stores/chatStore";
import ChatBubble from "./ChatBubble";
import ConfirmCard from "./ConfirmCard";
import MessageInput from "./MessageInput";
import SourceDrawer from "../SourceDrawer";

interface ChatAreaProps {
  onSend: (question: string, scene: string) => void;
  onCancel: () => void;
}

export default function ChatArea({ onSend, onCancel }: ChatAreaProps) {
  const messages = useChatStore((s) => s.messages);
  const phase = useChatStore((s) => s.currentPhase);
  const streamText = useChatStore((s) => s.currentStreamText);
  const reasoningText = useChatStore((s) => s.currentReasoningText);
  const sources = useChatStore((s) => s.currentSources);
  const confidence = useChatStore((s) => s.currentConfidence);
  const confidenceScore = useChatStore((s) => s.currentConfidenceScore);
  const logId = useChatStore((s) => s.currentLogId);
  const traceId = useChatStore((s) => s.currentTraceId);
  const lastQuestion = useChatStore((s) => s.lastQuestion);

  const [drawerChunkId, setDrawerChunkId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamText, phase]);

  const isStreaming = phase === "streaming";
  const isVerifying = phase === "verifying";
  const isProcessing = phase !== "idle" && phase !== "done" && phase !== "error";

  const streamMessage =
    isStreaming || isVerifying || phase === "done"
      ? {
          id: "stream",
          role: "assistant" as const,
          content: streamText,
          reasoning_content: reasoningText,
          sources: phase === "done" ? sources : undefined,
          confidence: phase === "done" ? (confidence ?? undefined) : undefined,
          confidence_score: phase === "done" ? (confidenceScore ?? undefined) : undefined,
          log_id: phase === "done" ? (logId ?? undefined) : undefined,
          trace_id: phase === "done" ? (traceId ?? undefined) : undefined,
          timestamp: new Date().toISOString(),
        }
      : null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-2" aria-live="polite">
        {messages.length === 0 && !streamMessage && (
          <div className="flex h-full items-center justify-center text-center text-gray-400">
            <div>
              <p className="text-lg">欢迎！有什么可以帮你的？</p>
              <p className="mt-1 text-sm">输入问题，开始查询企业知识库</p>
            </div>
          </div>
        )}
        {messages.map((m) => {
          if (m.role === "confirmation" && m.confirmation) {
            return (
              <ConfirmCard
                key={m.id}
                confirmation={m.confirmation}
                onChoice={(_choice) => {
                  // Visual state is handled internally by ConfirmCard.
                  // We keep the message in history as-is.
                }}
              />
            );
          }
          return (
            <ChatBubble
              key={m.id}
              message={m}
              onSourceClick={(chunkId) => setDrawerChunkId(chunkId)}
            />
          );
        })}
        {streamMessage && (
          <ChatBubble
            message={streamMessage}
            isStreaming={isStreaming}
            onSourceClick={(chunkId) => setDrawerChunkId(chunkId)}
          />
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex-shrink-0 border-t bg-gray-50 px-4 py-2 text-center text-xs text-gray-400">
        ⚠️ 答案仅供参考，重要决策请以官方文档或人工咨询为准
      </div>

      <MessageInput
        onSend={onSend}
        onCancel={onCancel}
        disabled={isProcessing}
        lastQuestion={lastQuestion}
      />

      <SourceDrawer
        chunkId={drawerChunkId}
        onClose={() => setDrawerChunkId(null)}
      />
    </div>
  );
}
