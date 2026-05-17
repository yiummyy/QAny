export const QUERY_KEYS = {
  auth: {
    me: ["auth", "me"] as const,
  },
  admin: {
    settings: ["admin", "settings"] as const,
    metrics: ["admin", "metrics"] as const,
    logs: (filters: Record<string, unknown>) => ["admin", "logs", filters] as const,
  },
  knowledge: {
    documents: (filters?: Record<string, unknown>) =>
      ["knowledge", "documents", filters ?? {}] as const,
  },
  qa: {
    session: (sessionId: string) => ["qa", "session", sessionId] as const,
    chunk: (chunkId: string) => ["qa", "chunk", chunkId] as const,
  },
} as const;

export const CONFIDENCE_LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};
