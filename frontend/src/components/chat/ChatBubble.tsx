import { useState, useEffect } from "react";
import type { ChatMessage } from "../../types/qa";
import StreamingText from "./StreamingText";
import MarkdownContent from "./MarkdownContent";
import ConfidenceBadge from "./ConfidenceBadge";
import CitationBadge from "./CitationBadge";
import SourceList from "./SourceList";
import ChatFeedback from "./ChatFeedback";

interface ChatBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
  onSourceClick?: (chunkId: string) => void;
}

export default function ChatBubble({
  message,
  isStreaming = false,
  onSourceClick,
}: ChatBubbleProps) {
  const [showReasoning, setShowReasoning] = useState(isStreaming);

  useEffect(() => {
    if (!isStreaming) {
      setShowReasoning(false);
    }
  }, [isStreaming]);

  if (message.role === "status") {
    return (
      <div className="my-2 flex justify-center">
        <div className="inline-flex items-center gap-2 rounded-full bg-gray-50 px-3 py-1 text-xs text-gray-500 border border-gray-100">
          <span className="flex h-3 w-3 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
          </span>
          {message.content}
        </div>
      </div>
    );
  }

  if (message.role === "error") {
    return (
      <div className="my-2 flex justify-start">
        <div className="max-w-[80%] rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {message.content}
        </div>
      </div>
    );
  }

  const isUser = message.role === "user";

  return (
    <div className={`my-3 flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2.5 text-sm ${
          isUser
            ? "bg-blue-600 text-white"
            : "border bg-white text-gray-800 shadow-sm"
        }`}
        aria-label={isUser ? "你的问题" : "AI 回答"}
      >
        {!isUser && message.reasoning_content && (
          <div className="mb-2">
            <button
              onClick={() => setShowReasoning(!showReasoning)}
              className="flex items-center gap-1 text-xs font-medium text-gray-500 hover:text-gray-700 focus:outline-none"
            >
              <span>{showReasoning ? "▼" : "▶"}</span>
              <span>思考过程</span>
            </button>
            {showReasoning && (
              <div className="mt-2 mb-3 rounded bg-gray-50 p-3 text-xs text-gray-600 border border-gray-100">
                <StreamingText text={message.reasoning_content} isStreaming={isStreaming && !message.content} />
              </div>
            )}
          </div>
        )}

        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : isStreaming ? (
          <StreamingText text={message.content} isStreaming={true} />
        ) : (
          <MarkdownContent text={message.content} />
        )}

        {!isUser && !isStreaming && message.confidence && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <ConfidenceBadge
              confidence={message.confidence}
              score={message.confidence_score ?? null}
            />
          </div>
        )}

        {!isUser && !isStreaming && message.citations && (
          <CitationBadge citations={message.citations} />
        )}

        {!isUser && !isStreaming && message.sources && message.sources.length > 0 && (
          <SourceList sources={message.sources} onSelect={onSourceClick ?? (() => {})} />
        )}

        {!isUser && !isStreaming && (
          <ChatFeedback logId={message.log_id ?? null} />
        )}
      </div>
    </div>
  );
}
