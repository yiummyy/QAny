import { create } from "zustand";
import type { ChatPhase, ChatMessage, SourceItem } from "../types/qa";

function genId(): string {
  return crypto.randomUUID?.() ??
    `id_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

export interface Session {
  id: string;
  title: string;
  createdAt: string;
}

// ---- localStorage persistence ----
const LS_SESSIONS = "qa_sessions";
const LS_MSG_PREFIX = "qa_msgs_";

function loadSessions(): Session[] {
  try {
    const raw = localStorage.getItem(LS_SESSIONS);
    return raw ? (JSON.parse(raw) as Session[]) : [];
  } catch { return []; }
}

function saveSessions(sessions: Session[]) {
  try { localStorage.setItem(LS_SESSIONS, JSON.stringify(sessions)); } catch {}
}

function loadMessages(sessionId: string): ChatMessage[] {
  try {
    const raw = localStorage.getItem(LS_MSG_PREFIX + sessionId);
    return raw ? (JSON.parse(raw) as ChatMessage[]) : [];
  } catch { return []; }
}

function saveMessages(sessionId: string, messages: ChatMessage[]) {
  try {
    // Keep only the last 200 messages to avoid localStorage quota
    const trimmed = messages.slice(-200);
    localStorage.setItem(LS_MSG_PREFIX + sessionId, JSON.stringify(trimmed));
  } catch {}
}

function removeMessages(sessionId: string) {
  try { localStorage.removeItem(LS_MSG_PREFIX + sessionId); } catch {}
}

interface ChatState {
  sessions: Session[];
  activeSessionId: string | null;
  messages: ChatMessage[];
  currentPhase: ChatPhase;
  currentStreamText: string;
  currentReasoningText: string;
  currentSources: SourceItem[];
  currentConfidence: "high" | "medium" | "low" | null;
  currentConfidenceScore: number | null;
  currentLogId: string | null;
  currentTraceId: string | null;
  lastQuestion: string;

  setSessions: (sessions: Session[]) => void;
  setActiveSessionId: (id: string) => void;
  setPhase: (phase: ChatPhase, statusMessage?: string) => void;
  appendStreamChunk: (chunk: string, reasoningChunk?: string) => void;
  setStreamResult: (data: {
    answer: string;
    sources: SourceItem[];
    confidence: "high" | "medium" | "low";
    confidence_score: number;
    trace_id: string;
  }) => void;
  addMessage: (msg: ChatMessage) => void;
  resetCurrentQA: () => void;
  newSession: () => string;
  updateSessionTitle: (id: string, title: string) => void;
  deleteSession: (id: string) => void;
  loadSessionMessages: (id: string) => void;
}

const initialSessions = loadSessions();

export const useChatStore = create<ChatState>((set) => ({
  sessions: initialSessions,
  activeSessionId: initialSessions.length > 0 ? initialSessions[0].id : null,
  messages: initialSessions.length > 0 ? loadMessages(initialSessions[0].id) : [],
  currentPhase: "idle",
  currentStreamText: "",
  currentReasoningText: "",
  currentSources: [],
  currentConfidence: null,
  currentConfidenceScore: null,
  currentLogId: null,
  currentTraceId: null,
  lastQuestion: "",

  setSessions: (sessions) => set({ sessions }),

  setActiveSessionId: (id) => set({ activeSessionId: id }),

  setPhase: (phase, statusMessage) => {
    set((s) => {
      // Remove any existing status messages
      const filteredMessages = s.messages.filter((m) => m.role !== "status");

      if (statusMessage && phase !== "done" && phase !== "error") {
        const msg: ChatMessage = {
          id: genId(),
          role: "status",
          content: statusMessage,
          timestamp: new Date().toISOString(),
        };
        return { currentPhase: phase, messages: [...filteredMessages, msg] };
      } else {
        return { currentPhase: phase, messages: filteredMessages };
      }
    });
  },

  appendStreamChunk: (chunk, reasoningChunk = "") =>
    set((s) => ({
      currentStreamText: s.currentStreamText + chunk,
      currentReasoningText: s.currentReasoningText + reasoningChunk
    })),

  setStreamResult: (data) =>
    set({
      currentConfidence: data.confidence,
      currentConfidenceScore: data.confidence_score,
      currentSources: data.sources,
      currentTraceId: data.trace_id,
    }),

  addMessage: (msg) =>
    set((s) => {
      const updated = [...s.messages, msg];
      if (s.activeSessionId) saveMessages(s.activeSessionId, updated);
      return { messages: updated };
    }),

  resetCurrentQA: () =>
    set((s) => ({
      currentPhase: "idle",
      currentStreamText: "",
      currentReasoningText: "",
      currentSources: [],
      currentConfidence: null,
      currentConfidenceScore: null,
      currentLogId: null,
      currentTraceId: null,
      messages: s.messages.filter((m) => m.role !== "status"),
    })),

  newSession: () => {
    const id = genId();
    const session: Session = {
      id,
      title: "新会话",
      createdAt: new Date().toISOString(),
    };
    set((s) => {
      const updated = [session, ...s.sessions];
      saveSessions(updated);
      if (s.activeSessionId) saveMessages(s.activeSessionId, s.messages);
      return {
        sessions: updated,
        activeSessionId: id,
        messages: [],
        currentPhase: "idle",
        currentStreamText: "",
        currentReasoningText: "",
        currentSources: [],
        currentConfidence: null,
        currentConfidenceScore: null,
        currentLogId: null,
        currentTraceId: null,
        lastQuestion: "",
      };
    });
    return id;
  },

  updateSessionTitle: (id, title) =>
    set((s) => {
      const updated = s.sessions.map((ses) =>
        ses.id === id ? { ...ses, title } : ses
      );
      saveSessions(updated);
      return { sessions: updated };
    }),

  deleteSession: (id: string) =>
    set((s) => {
      const remaining = s.sessions.filter((ses) => ses.id !== id);
      const wasActive = s.activeSessionId === id;
      saveSessions(remaining);
      removeMessages(id);
      return {
        sessions: remaining,
        activeSessionId: wasActive
          ? (remaining.length > 0 ? remaining[0].id : null)
          : s.activeSessionId,
        ...(wasActive ? {
          messages: remaining.length > 0 ? loadMessages(remaining[0].id) : [],
          currentPhase: "idle" as const,
          currentStreamText: "",
          currentReasoningText: "",
          currentSources: [],
          currentConfidence: null,
          currentConfidenceScore: null,
          currentLogId: null,
          currentTraceId: null,
          lastQuestion: "",
        } : {}),
      };
    }),

  loadSessionMessages: (id: string) => {
    set((s) => {
      if (s.activeSessionId && s.activeSessionId !== id) {
        saveMessages(s.activeSessionId, s.messages);
      }
      const msgs = loadMessages(id);
      return { activeSessionId: id, messages: msgs, currentPhase: "idle" };
    });
  },
}));
