import { useEffect, useRef } from "react";

interface ShortcutHandlers {
  onSubmit?: () => void;
  onCancel?: () => void;
  onRecallLast?: () => void;
  enabled?: boolean;
}

export function useKeyboardShortcuts({
  onSubmit,
  onCancel,
  onRecallLast,
  enabled = true,
}: ShortcutHandlers) {
  const refs = useRef({ onSubmit, onCancel, onRecallLast });
  refs.current = { onSubmit, onCancel, onRecallLast };

  useEffect(() => {
    if (!enabled) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        refs.current.onSubmit?.();
      } else if (e.key === "Escape") {
        e.preventDefault();
        refs.current.onCancel?.();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        refs.current.onRecallLast?.();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [enabled]);
}
