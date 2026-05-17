import { useState } from "react";
import type { CitationReport } from "../../types/qa";

interface Props {
  citations: CitationReport;
}

export default function CitationBadge({ citations }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (!citations || (citations.verified.length === 0 && citations.unverified.length === 0 && citations.orphan_claims.length === 0)) {
    return null;
  }

  const verifiedCount = citations.verified.length;
  const unverifiedCount = citations.unverified.length;
  const orphanCount = citations.orphan_claims.length;
  const totalRefs = verifiedCount + unverifiedCount;

  const statusIcon =
    citations.overall_score >= 0.8 ? "✓" :
    citations.overall_score >= 0.6 ? "⚠" : "✗";

  const statusColor =
    citations.overall_score >= 0.8 ? "text-green-600" :
    citations.overall_score >= 0.6 ? "text-yellow-600" : "text-red-600";

  return (
    <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className={`font-medium ${statusColor}`}>
          {statusIcon} 引用验证 · 覆盖率 {Math.round(citations.coverage * 100)}% ·{" "}
          通过 {verifiedCount}/{totalRefs}
          {unverifiedCount > 0 && ` · 存疑 ${unverifiedCount}`}
          {orphanCount > 0 && ` · 无来源 ${orphanCount}`}
        </span>
        <span className="text-gray-400">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="mt-2 space-y-2 border-t border-gray-200 pt-2">
          {citations.verified.map((v) => (
            <div key={v.anchor} className="flex items-start gap-1 text-green-700">
              <span className="shrink-0 font-medium">✓ [{v.anchor}]</span>
              <span className="break-all">
                {v.sentence}
                <span className="text-green-500 ml-1">
                  ({Math.round(v.similarity * 100)}%)
                </span>
              </span>
            </div>
          ))}
          {citations.unverified.map((v) => (
            <div key={v.anchor} className="flex items-start gap-1">
              <span className={`shrink-0 font-medium ${v.status === "mismatched" ? "text-red-600" : "text-yellow-600"}`}>
                {v.status === "mismatched" ? "✗" : "⚠"} [{v.anchor}]
              </span>
              <span className={`break-all ${v.status === "mismatched" ? "text-red-700" : "text-yellow-700"}`}>
                {v.sentence}
                <span className="ml-1 opacity-60">
                  ({Math.round(v.similarity * 100)}%)
                </span>
              </span>
            </div>
          ))}
          {citations.orphan_claims.map((o, i) => (
            <div key={i} className="flex items-start gap-1 text-orange-600">
              <span className="shrink-0 font-medium">? [{o.claim_type}]</span>
              <span className="break-all underline decoration-dotted underline-offset-2">
                {o.sentence}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
