import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listDocuments, deleteDocument, syncKnowledge } from "../../../api/knowledge";
import { QUERY_KEYS } from "../../../lib/constants";
import { formatDate } from "../../../lib/format";
import LoadingSpinner from "../../common/LoadingSpinner";
import ErrorBanner from "../../common/ErrorBanner";
import StatusBadge from "../../common/StatusBadge";
import Pagination from "../../common/Pagination";
import ConfirmDialog from "../../common/ConfirmDialog";
import { toast } from "../../common/Toast";
import DocumentPreviewModal from "./DocumentPreviewModal";

export default function DocumentTable() {
  const queryClient = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [permissionFilter, setPermissionFilter] = useState("");
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [previewId, setPreviewId] = useState<{ id: string; title: string } | null>(null);
  const [syncing, setSyncing] = useState(false);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: QUERY_KEYS.knowledge.documents({ offset, statusFilter, permissionFilter }),
    queryFn: () =>
      listDocuments({
        offset,
        limit: 20,
        status_filter: statusFilter || undefined,
        permission_level: permissionFilter || undefined,
      }),
  });

  const deleteMut = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.knowledge.documents() });
      toast("文档已删除", "success");
    },
    onError: () => toast("删除失败", "error"),
  });

  async function handleSync() {
    setSyncing(true);
    try {
      const res = await syncKnowledge();
      toast(res.message, "success");
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.knowledge.documents() });
    } catch {
      toast("同步失败", "error");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="mt-4">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setOffset(0); }}
          className="rounded border px-2 py-1 text-sm"
        >
          <option value="">全部状态</option>
          <option value="pending">待处理</option>
          <option value="indexed">已索引</option>
          <option value="failed">失败</option>
        </select>
        <select
          value={permissionFilter}
          onChange={(e) => { setPermissionFilter(e.target.value); setOffset(0); }}
          className="rounded border px-2 py-1 text-sm"
        >
          <option value="">全部级别</option>
          <option value="L1">L1</option>
          <option value="L2">L2</option>
          <option value="L3">L3</option>
        </select>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="rounded border px-3 py-1 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-60"
        >
          {syncing ? "同步中..." : "重建索引"}
        </button>
      </div>

      {isLoading && <LoadingSpinner />}
      {error && <ErrorBanner message="加载文档列表失败" onRetry={() => refetch()} />}

      {data && data.items.length === 0 && (
        <p className="py-8 text-center text-sm text-gray-400">暂无知识文档</p>
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-2 font-medium">文档名称</th>
                  <th className="pb-2 font-medium">类型</th>
                  <th className="pb-2 font-medium">标签</th>
                  <th className="pb-2 font-medium">权限</th>
                  <th className="pb-2 font-medium">状态</th>
                  <th className="pb-2 font-medium">分块数</th>
                  <th className="pb-2 font-medium">上传时间</th>
                  <th className="pb-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((doc) => (
                  <tr key={doc.doc_id} className="border-b text-gray-700">
                    <td className="py-2 pr-4 max-w-[200px] truncate" title={doc.title}>
                      {doc.title}
                    </td>
                    <td className="py-2">{doc.source_type}</td>
                    <td className="py-2">
                      {doc.tags && doc.tags.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {doc.tags.map((tag) => (
                            <span
                              key={tag}
                              className="inline-block rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-gray-300">-</span>
                      )}
                    </td>
                    <td className="py-2">{doc.permission_level}</td>
                    <td className="py-2">
                      <StatusBadge status={doc.status} />
                    </td>
                    <td className="py-2">{doc.chunk_count}</td>
                    <td className="py-2 text-xs text-gray-400">
                      {formatDate(doc.uploaded_at)}
                    </td>
                    <td className="py-2 flex items-center gap-2">
                      <button
                        onClick={() => setPreviewId({ id: doc.doc_id, title: doc.title })}
                        className="text-blue-500 hover:underline text-xs"
                      >
                        预览
                      </button>
                      <button
                        onClick={() => setDeleteId(doc.doc_id)}
                        className="text-red-500 hover:underline text-xs"
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3">
            <Pagination
              offset={offset}
              limit={20}
              total={data.total}
              onChange={setOffset}
            />
          </div>
        </>
      )}

      <ConfirmDialog
        open={!!deleteId}
        title="删除文档"
        message="确定要删除该文档及其所有分块吗？此操作不可恢复。"
        confirmLabel="删除"
        onConfirm={() => {
          if (deleteId) deleteMut.mutate(deleteId);
          setDeleteId(null);
        }}
        onCancel={() => setDeleteId(null)}
      />

      <DocumentPreviewModal
        open={!!previewId}
        docId={previewId?.id ?? null}
        docTitle={previewId?.title ?? null}
        onClose={() => setPreviewId(null)}
      />
    </div>
  );
}
