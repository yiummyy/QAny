const COLORS: Record<string, string> = {
  high: "bg-green-100 text-green-800",
  medium: "bg-yellow-100 text-yellow-800",
  low: "bg-red-100 text-red-800",
};

const LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

export default function ConfidenceBadge({
  confidence,
  score,
}: {
  confidence: string | null;
  score: number | null;
}) {
  if (!confidence) return null;

  const pct = score != null ? ` ${Math.round(score * 100)}%` : "";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
        COLORS[confidence] ?? "bg-gray-100 text-gray-700"
      }`}
    >
      置信度：{LABELS[confidence] ?? confidence}{pct}
    </span>
  );
}
