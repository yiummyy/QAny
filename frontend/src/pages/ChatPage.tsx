import { useCallback, useState } from "react";
import { useChatStore } from "../stores/chatStore";
import { useSSE } from "../hooks/useSSE";
import ChatArea from "../components/chat/ChatArea";
import Sidebar from "../components/layout/Sidebar";
import { toast } from "../components/common/Toast";
import type { ChatMessage } from "../types/qa";

export default function ChatPage() {
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const newSession = useChatStore((s) => s.newSession);
  const addMessage = useChatStore((s) => s.addMessage);
  const setPhase = useChatStore((s) => s.setPhase);
  const appendStreamChunk = useChatStore((s) => s.appendStreamChunk);
  const setStreamResult = useChatStore((s) => s.setStreamResult);
  const resetCurrentQA = useChatStore((s) => s.resetCurrentQA);
  const updateSessionTitle = useChatStore((s) => s.updateSessionTitle);
  const sessions = useChatStore((s) => s.sessions);
  const { connect, cancel } = useSSE();
  const [mobileSidebar, setMobileSidebar] = useState(false);

  // Ensure a session exists
  const sessionId = activeSessionId ?? newSession();

  const handleSend = useCallback(
    async (question: string, scene: string) => {
      // Update session title from first question
      const isFirst = sessions.find((s) => s.id === sessionId)?.title === "新会话";
      if (isFirst) {
        updateSessionTitle(sessionId, question.slice(0, 30));
      }

      const userMsg: ChatMessage = {
        id: crypto.randomUUID?.() ?? `u_${Date.now()}`,
        role: "user",
        content: question,
        timestamp: new Date().toISOString(),
      };
      addMessage(userMsg);
      setPhase("pending");
      setMobileSidebar(false);

      let fullAnswer = "";
      let fullReasoning = "";

      // Pass all phase status messages to the store so the user sees the fine-grained steps
      await connect(question, sessionId, {
        onPhaseChange: (phase, statusMsg) => {
          setPhase(phase, statusMsg);
        },
        onChunk: (text, reasoning) => {
          fullAnswer += text;
          if (reasoning) {
            fullReasoning += reasoning;
          }
          appendStreamChunk(text, reasoning);
        },
        onDone: (data) => {
          setStreamResult(data);
          setPhase("done");
          const answerText = data.answer || fullAnswer || "系统处理完成，请查看引用来源。";
          const aiMsg: ChatMessage = {
            id: crypto.randomUUID?.() ?? `ai_${Date.now()}`,
            role: "assistant",
            content: answerText,
            reasoning_content: fullReasoning,
            sources: data.sources,
            confidence: data.confidence,
            confidence_score: data.confidence_score,
            trace_id: data.trace_id,
            citations: data.citations ?? null,
            timestamp: new Date().toISOString(),
          };
          addMessage(aiMsg);
          resetCurrentQA();
        },
        onConfirmRequired: (data) => {
          const confirmMsg: ChatMessage = {
            id: crypto.randomUUID?.() ?? `cfm_${Date.now()}`,
            role: "confirmation",
            content: data.summary,
            confirmation: data,
            timestamp: new Date().toISOString(),
          };
          addMessage(confirmMsg);
        },
        onError: (code, msg, fallback) => {
          setPhase("error");
          const content = fallback ?? msg;
          const errorMsg: ChatMessage = {
            id: crypto.randomUUID?.() ?? `err_${Date.now()}`,
            role: "error",
            content: `[${code}] ${content}`,
            timestamp: new Date().toISOString(),
          };
          addMessage(errorMsg);
          resetCurrentQA();
          if (code >= 50900) {
            toast(content, "error");
          }
        },
      }, scene);
    },
    [
      sessionId,
      sessions,
      connect,
      addMessage,
      setPhase,
      appendStreamChunk,
      setStreamResult,
      resetCurrentQA,
      updateSessionTitle,
    ],
  );

  const handleCancel = useCallback(() => {
    cancel();
    resetCurrentQA();
  }, [cancel, resetCurrentQA]);

  const loadSessionMessages = useChatStore((s) => s.loadSessionMessages);

  const handleSelectSession = useCallback(
    (id: string) => {
      loadSessionMessages(id);
    },
    [loadSessionMessages],
  );

  return (
    <div className="flex h-full">
      {/* Desktop sidebar */}
      <div className="hidden md:block">
        <Sidebar
          onSelectSession={handleSelectSession}
        />
      </div>

      {/* Mobile sidebar overlay */}
      {mobileSidebar && (
        <div className="fixed inset-0 z-30 md:hidden">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setMobileSidebar(false)}
          />
          <div className="absolute left-0 top-0 h-full w-56 bg-white">
            <Sidebar
              onSelectSession={handleSelectSession}
            />
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <ChatArea onSend={handleSend} onCancel={handleCancel} />
      </div>
    </div>
  );
}
