import apiClient, { handleApiError } from "./client";
import type { FeedbackRequest, FeedbackResponse } from "../types/feedback";

export async function submitFeedback(
  body: FeedbackRequest,
): Promise<FeedbackResponse> {
  try {
    const resp = await apiClient.post<FeedbackResponse>("/feedback", body);
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}
