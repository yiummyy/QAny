export default function ErrorBanner({
  code,
  message,
  onRetry,
}: {
  code?: number;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
      role="alert"
    >
      <div className="flex items-center gap-2">
        <span className="font-medium">
          {code ? `错误 ${code}` : "错误"}
        </span>
        <span className="text-red-600">{message}</span>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 text-sm font-medium text-red-700 underline hover:text-red-800"
        >
          重试
        </button>
      )}
    </div>
  );
}
