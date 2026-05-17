import { useState } from "react";
import { submitFeedback } from "../../api/feedback";
import { toast } from "../common/Toast";

export default function ChatFeedback({ logId }: { logId: string | null }) {
  const [submitted, setSubmitted] = useState<string | null>(null);

  async function handle(type: "thumbs_up" | "thumbs_down") {
    if (!logId || submitted) return;
    try {
      await submitFeedback({ log_id: logId, feedback_type: type });
      setSubmitted(type);
      toast("反馈已提交", "success");
    } catch {
      toast("反馈提交失败", "error");
    }
  }

  return (
    <div className="mt-2 flex items-center gap-1">
      <button
        onClick={() => handle("thumbs_up")}
        disabled={!!submitted}
        aria-label="点赞"
        className={`rounded px-2 py-0.5 text-sm transition-colors ${
          submitted === "thumbs_up"
            ? "text-green-600"
            : "text-gray-400 hover:text-green-600"
        } disabled:cursor-default`}
      >
        {submitted === "thumbs_up" ? "已" : ""}有帮助
      </button>
      <button
        onClick={() => handle("thumbs_down")}
        disabled={!!submitted}
        aria-label="点踩"
        className={`rounded px-2 py-0.5 text-sm transition-colors ${
          submitted === "thumbs_down"
            ? "text-red-600"
            : "text-gray-400 hover:text-red-600"
        } disabled:cursor-default`}
      >
        {submitted === "thumbs_down" ? "已" : ""}无帮助
      </button>
    </div>
  );
}
