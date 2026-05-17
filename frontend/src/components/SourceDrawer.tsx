import { useState, useEffect } from "react";
import { getChunk } from "../api/qa";
import type { ChunkDetail } from "../types/qa";
import LoadingSpinner from "./common/LoadingSpinner";

export default function SourceDrawer({
  chunkId,
  onClose,
}: {
  chunkId: string | null;
  onClose: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [chunk, setChunk] = useState<ChunkDetail | null>(null);

  useEffect(() => {
    if (!chunkId) {
      setChunk(null);
      return;
    }
    setLoading(true);
    setError("");
    getChunk(chunkId)
      .then(setChunk)
      .catch(() => setError("无法加载原文"))
      .finally(() => setLoading(false));
  }, [chunkId]);

  const open = chunkId !== null;

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/30"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <div
        className={`fixed right-0 top-0 z-50 h-full w-full max-w-lg transform border-l bg-white shadow-xl transition-transform duration-200 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
        role="dialog"
        aria-label="原文详情"
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <h3 className="font-medium text-gray-900">
              {chunk?.doc_name ?? "来源详情"}
            </h3>
            <button
              onClick={onClose}
              className="rounded px-2 py-1 text-gray-400 hover:text-gray-600"
              aria-label="关闭"
            >
              ✕
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {loading && <LoadingSpinner label="加载中..." />}
            {error && <p className="text-center text-sm text-red-500 py-8">{error}</p>}
            {chunk && (
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2 text-xs text-gray-500">
                  <span className="rounded bg-gray-100 px-2 py-0.5">
                    权限：{chunk.permission_level}
                  </span>
                  <span className="rounded bg-gray-100 px-2 py-0.5">
                    {chunk.section ?? "正文"}
                  </span>
                  <span className="rounded bg-gray-100 px-2 py-0.5">
                    第 {chunk.chunk_index + 1} 段
                  </span>
                </div>
                <pre className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800 font-sans">
                  {chunk.content}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
