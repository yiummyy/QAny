import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getSession } from "../api/qa";
import { QUERY_KEYS } from "../lib/constants";
import Sidebar from "../components/layout/Sidebar";
import ChatBubble from "../components/chat/ChatBubble";
import LoadingSpinner from "../components/common/LoadingSpinner";
import ErrorBanner from "../components/common/ErrorBanner";
import SourceDrawer from "../components/SourceDrawer";
import type { ChatMessage } from "../types/qa";

function recordsToMessages(
  records: Array<Record<string, unknown>>,
): ChatMessage[] {
  return records
    .filter((r) => r.type === "user" || r.type === "assistant_done" || r.type === "error")
    .map((r) => {
      const ts = (r.ts as string) ?? new Date().toISOString();
      if (r.type === "user") {
        return {
          id: ts,
          role: "user" as const,
          content: (r.content as string) ?? "",
          timestamp: ts,
        };
      }
      if (r.type === "error") {
        return {
          id: ts,
          role: "error" as const,
          content: (r.message as string) ?? "未知错误",
          timestamp: ts,
        };
      }
      return {
          id: ts,
          role: "assistant" as const,
          content: (r.content as string) ?? "",
          sources: (r.sources as ChatMessage["sources"]) ?? undefined,
          confidence: (r.confidence as ChatMessage["confidence"]) ?? undefined,
          timestamp: ts,
        };
    });
}

export default function HistoryPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerChunkId, setDrawerChunkId] = useState<string | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: QUERY_KEYS.qa.session(selectedId ?? ""),
    queryFn: () => getSession(selectedId!),
    enabled: !!selectedId,
  });

  const messages = data ? recordsToMessages(data.records as Array<Record<string, unknown>>) : [];

  return (
    <div className="flex h-full">
      <div className="hidden md:block">
        <Sidebar
          onSelectSession={setSelectedId}
          activeId={selectedId}
          showNewButton={false}
        />
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
        {!selectedId && (
          <div className="flex h-full items-center justify-center text-center text-gray-400">
            <div>
              <p className="text-lg">选择会话查看历史</p>
              <p className="mt-1 text-sm">从左侧选择一个会话记录</p>
            </div>
          </div>
        )}

        {selectedId && isLoading && <LoadingSpinner label="加载会话..." />}

        {selectedId && error && (
          <ErrorBanner message="加载会话失败" onRetry={() => refetch()} />
        )}

        {selectedId && !isLoading && !error && messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-gray-400">
            该会话暂无记录
          </div>
        )}

        {messages.map((m) => (
          <ChatBubble
            key={m.id}
            message={m}
            onSourceClick={(chunkId) => setDrawerChunkId(chunkId)}
          />
        ))}
      </div>

      <SourceDrawer
        chunkId={drawerChunkId}
        onClose={() => setDrawerChunkId(null)}
      />
    </div>
  );
}
