export default function LoadingSpinner({
  size = "md",
  label,
}: {
  size?: "sm" | "md" | "lg";
  label?: string;
}) {
  const sizeClass = {
    sm: "h-4 w-4 border-2",
    md: "h-8 w-8 border-2",
    lg: "h-12 w-12 border-3",
  }[size];

  return (
    <div className="flex flex-col items-center justify-center gap-2 py-8" role="status">
      <div
        className={`${sizeClass} animate-spin rounded-full border-gray-300 border-t-blue-600`}
      />
      {label && <span className="text-sm text-gray-500">{label}</span>}
    </div>
  );
}
