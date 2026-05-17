const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  parsing: "bg-blue-100 text-blue-800",
  indexed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  success: "bg-green-100 text-green-800",
  fallback: "bg-yellow-100 text-yellow-800",
  error: "bg-red-100 text-red-800",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  parsing: "解析中",
  indexed: "已索引",
  failed: "失败",
  success: "成功",
  fallback: "降级",
  error: "错误",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
        STATUS_COLORS[status] ?? "bg-gray-100 text-gray-700"
      }`}
    >
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}
