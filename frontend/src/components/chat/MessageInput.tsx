import { useState, useRef, useEffect } from "react";

interface MessageInputProps {
  onSend: (text: string, scene: string) => void;
  onCancel?: () => void;
  disabled?: boolean;
  lastQuestion?: string;
}

const SCENES: { value: string; label: string; icon: string }[] = [
  { value: "general", label: "综合", icon: "💬" },
  { value: "ticket", label: "工单", icon: "🎫" },
  { value: "sales", label: "营销", icon: "📈" },
  { value: "ops", label: "运维", icon: "⚙️" },
];

export default function MessageInput({
  onSend,
  onCancel,
  disabled,
  lastQuestion,
}: MessageInputProps) {
  const [text, setText] = useState("");
  const [scene, setScene] = useState("general");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!disabled && ref.current) ref.current.focus();
  }, [disabled]);

  function handleSend() {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, scene);
    setText("");
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleSend();
    } else if (e.key === "Escape") {
      e.preventDefault();
      onCancel?.();
      setText("");
    } else if (e.key === "ArrowUp" && !text && lastQuestion) {
      e.preventDefault();
      setText(lastQuestion);
    }
  }

  return (
    <div className="border-t bg-white px-4 py-3">
      {/* Scene pill selector */}
      <div className="mb-3 flex items-center gap-1.5">
        {SCENES.map((s) => (
          <button
            key={s.value}
            onClick={() => setScene(s.value)}
            disabled={disabled}
            className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium transition-all duration-200 ${
              s.value === scene
                ? "bg-blue-600 text-white shadow-sm shadow-blue-200"
                : "bg-gray-100 text-gray-500 hover:bg-gray-200 hover:text-gray-700"
            } disabled:opacity-50`}
            aria-pressed={s.value === scene}
          >
            <span className="text-xs leading-none">{s.icon}</span>
            <span>{s.label}</span>
          </button>
        ))}
      </div>

      {/* Input row */}
      <div
        className={`flex items-end gap-2 rounded-2xl border bg-gray-50 px-3 py-2 transition-all duration-200 ${
          disabled
            ? "border-gray-200"
            : "border-gray-200 focus-within:border-blue-400 focus-within:bg-white focus-within:shadow-md focus-within:shadow-blue-100/50"
        }`}
      >
        <textarea
          ref={ref}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="输入问题..."
          rows={1}
          className="flex-1 resize-none bg-transparent py-1 text-sm placeholder-gray-400 outline-none disabled:text-gray-400"
          aria-label="输入问题"
        />
        {disabled ? (
          <button
            onClick={onCancel}
            className="flex-shrink-0 rounded-full bg-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-400"
            aria-label="取消"
          >
            取消
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!text.trim()}
            className="flex-shrink-0 flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-white transition-all duration-200 hover:bg-blue-700 hover:shadow-md hover:shadow-blue-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:shadow-none disabled:active:scale-100"
            aria-label="发送"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M1 8L14 1L8.5 14.5L7 9L1 8Z"
                fill="currentColor"
                stroke="white"
                strokeWidth="1.2"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        )}
      </div>

      {/* Hint */}
      <p className="mt-1.5 text-right text-[11px] text-gray-400">
        Ctrl+Enter 发送 · Esc 取消 · ↑ 复用上一条
      </p>
    </div>
  );
}
