export type ChatPhase =
  | "idle"
  | "pending"
  | "planning"
  | "retrieving"
  | "searching"
  | "reranking"
  | "checking_permissions"
  | "generating"
  | "verifying"
  | "thinking"
  | "streaming"
  | "long_wait"
  | "confirming"
  | "confirmation_rejected"
  | "confirmation_timeout"
  | "done"
  | "error";

export interface AskRequest {
  question: string;
  session_id: string;
  input_type?: string;
  scene?: string;
}

export interface SourceItem {
  doc_id: string;
  doc_name: string;
  chunk_id: string;
  section: string;
  score: number;
}

export interface SSEDoneData {
  answer: string;
  sources: SourceItem[];
  confidence: "high" | "medium" | "low";
  confidence_score: number;
  citations?: CitationReport | null;
  steps: number;
  trace_id: string;
  response_time_ms: number;
}

export interface VerifiedCitation {
  anchor: string;
  sentence: string;
  chunk_id: string;
  similarity: number;
  status: "verified" | "suspicious" | "mismatched";
}

export interface OrphanClaim {
  sentence: string;
  claim_type: string;
}

export interface CitationReport {
  verified: VerifiedCitation[];
  unverified: VerifiedCitation[];
  orphan_claims: OrphanClaim[];
  coverage: number;
  overall_score: number;
}

export interface SSEErrorData {
  code: number;
  message: string;
  fallback_answer?: string;
}

export interface ChunkDetail {
  chunk_id: string;
  doc_id: string;
  doc_name: string;
  content: string;
  section: string;
  permission_level: string;
  chunk_index: number;
}

export interface SessionRecord {
  ts: string;
  type: string;
  content?: string;
  name?: string;
  summary?: string;
  message?: string;
  [key: string]: unknown;
}

export interface SessionHistory {
  session_id: string;
  records: SessionRecord[];
  count: number;
}

export interface ConfirmationRequestData {
  action_token: string;
  tool_name: string;
  tool_label: string;
  summary: string;
  details: Record<string, unknown>;
  expires_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "status" | "error" | "confirmation";
  content: string;
  reasoning_content?: string;
  sources?: SourceItem[];
  confidence?: "high" | "medium" | "low";
  confidence_score?: number;
  log_id?: string;
  trace_id?: string;
  timestamp: string;
  confirmation?: ConfirmationRequestData;
  confirmation_choice?: "approved" | "rejected" | "timeout";
  citations?: CitationReport | null;
}
