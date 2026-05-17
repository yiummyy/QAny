import apiClient, { handleApiError } from "./client";
import type { SessionHistory, ChunkDetail } from "../types/qa";

export async function getSession(sessionId: string): Promise<SessionHistory> {
  try {
    const resp = await apiClient.get<SessionHistory>(`/qa/sessions/${sessionId}`);
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}

export async function getChunk(chunkId: string): Promise<ChunkDetail> {
  try {
    const resp = await apiClient.get<ChunkDetail>(`/qa/chunks/${chunkId}`);
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}

export async function confirmAction(
  actionToken: string,
  choice: "approved" | "rejected",
): Promise<{ status: string; message: string }> {
  try {
    const resp = await apiClient.post<{ status: string; message: string }>(
      "/qa/confirm",
      { action_token: actionToken, choice },
    );
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}
