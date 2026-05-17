export interface FeedbackRequest {
  log_id: string;
  feedback_type: "thumbs_up" | "thumbs_down";
  reason?: string;
  comment?: string;
}

export interface FeedbackResponse {
  feedback_id: string;
  log_id: string;
  feedback_type: string;
  message: string;
}
