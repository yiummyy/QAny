export interface AdminSettings {
  config: Record<string, unknown>;
  updated_by: string | null;
  updated_at: string;
}

export interface UpdateSettingsRequest {
  config: Record<string, unknown>;
  updated_at: string;
}

export interface LogItem {
  log_id: string;
  session_id: string;
  user_id: string;
  scene: string;
  question: string;
  answer: string | null;
  confidence: string | null;
  confidence_score: number | null;
  status: string;
  error_code: number | null;
  trace_id: string | null;
  response_time_ms: number | null;
  created_at: string;
}

export interface LogListResponse {
  total: number;
  offset: number;
  limit: number;
  items: LogItem[];
}

export interface LogFilters {
  offset?: number;
  limit?: number;
  user_id?: string;
  status_filter?: string;
  scene?: string;
  date_from?: string;
  date_to?: string;
}

export interface Metrics {
  today_questions: number;
  success_rate: number;
  avg_response_ms: number;
  today_cost_rmb: number;
  today_tokens: number;
  feedback_thumbs_up: number;
  feedback_thumbs_down: number;
}
