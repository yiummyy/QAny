import apiClient, { handleApiError } from "./client";
import type {
  DocumentListResponse,
  UploadResponse,
  DeleteResponse,
  SyncResponse,
} from "../types/knowledge";

export async function uploadDocument(
  file: File,
  permissionLevel?: string,
  knowledgeBase?: string,
  tags?: string[],
): Promise<UploadResponse> {
  try {
    const formData = new FormData();
    formData.append("file", file);
    if (permissionLevel) {
      formData.append("permission_level", permissionLevel);
    }
    if (knowledgeBase) {
      formData.append("knowledge_base", knowledgeBase);
    }
    if (tags && tags.length > 0) {
      formData.append("tags", tags.join(","));
    }
    const resp = await apiClient.post<UploadResponse>(
      "/knowledge/upload",
      formData
    );
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}

export async function listDocuments(params?: {
  offset?: number;
  limit?: number;
  status_filter?: string;
  permission_level?: string;
}): Promise<DocumentListResponse> {
  try {
    const resp = await apiClient.get<DocumentListResponse>(
      "/knowledge/documents",
      { params },
    );
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}

export async function deleteDocument(docId: string): Promise<DeleteResponse> {
  try {
    const resp = await apiClient.delete<DeleteResponse>(
      `/knowledge/documents/${docId}`,
    );
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}

export async function syncKnowledge(): Promise<SyncResponse> {
  try {
    const resp = await apiClient.post<SyncResponse>("/knowledge/sync");
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}

export async function getDocumentContent(docId: string): Promise<{ doc_id: string; title: string; content: string }> {
  try {
    const resp = await apiClient.get<{ doc_id: string; title: string; content: string }>(
      `/knowledge/documents/${docId}/content`,
    );
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}
