import { useState, useEffect } from "react";
import { getDocumentContent } from "../../../api/knowledge";
import LoadingSpinner from "../../common/LoadingSpinner";
import { toast } from "../../common/Toast";

interface DocumentPreviewModalProps {
  open: boolean;
  docId: string | null;
  docTitle: string | null;
  onClose: () => void;
}

export default function DocumentPreviewModal({
  open,
  docId,
  docTitle,
  onClose,
}: DocumentPreviewModalProps) {
  const [content, setContent] = useState<string>("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open && docId) {
      setLoading(true);
      setContent("");
      getDocumentContent(docId)
        .then((res) => setContent(res.content))
        .catch(() => {
          toast("获取文档内容失败", "error");
          onClose();
        })
        .finally(() => setLoading(false));
    }
  }, [open, docId, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
      <div className="flex h-full max-h-[80vh] w-full max-w-3xl flex-col rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h3 className="text-lg font-semibold text-gray-900 truncate pr-4">
            预览: {docTitle}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-500 focus:outline-none"
          >
            <span className="sr-only">Close</span>
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6 bg-gray-50">
          {loading ? (
            <div className="flex h-full items-center justify-center">
              <LoadingSpinner />
            </div>
          ) : (
            <div className="whitespace-pre-wrap font-sans text-sm text-gray-800 bg-white p-6 rounded border shadow-sm min-h-full">
              {content || "该文档为空。"}
            </div>
          )}
        </div>
        <div className="border-t px-6 py-4 flex justify-end">
          <button
            onClick={onClose}
            className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-300"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}