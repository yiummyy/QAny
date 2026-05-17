import type { SourceItem } from "../../types/qa";

export default function SourceList({
  sources,
  onSelect,
}: {
  sources: SourceItem[];
  onSelect: (chunkId: string) => void;
}) {
  if (sources.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      <span className="text-xs text-gray-400">来源：</span>
      {sources.map((s) => (
        <button
          key={s.chunk_id}
          onClick={() => onSelect(s.chunk_id)}
          className="inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs text-blue-600 hover:bg-blue-50"
        >
          {s.doc_name}
          {s.section && <span className="text-gray-400">·{s.section}</span>}
        </button>
      ))}
    </div>
  );
}
