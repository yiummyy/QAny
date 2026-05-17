export interface DocumentItem {
  doc_id: string;
  title: string;
  source_type: string;
  knowledge_base: string;
  tags: string[] | null;
  permission_level: string;
  status: "pending" | "indexed" | "failed";
  chunk_count: number;
  uploaded_by: string | null;
  uploaded_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  total: number;
  items: DocumentItem[];
}

export interface UploadResponse {
  doc_id: string;
  title: string;
  status: string;
  message: string;
}

export interface DeleteResponse {
  doc_id: string;
  title: string;
  message: string;
}

export interface SyncResponse {
  message: string;
  document_count: number;
}
