import { useState, useRef, useEffect } from "react";
import { uploadDocument } from "../../../api/knowledge";
import { toast } from "../../common/Toast";

const ALLOWED_EXTS = [".pdf", ".docx", ".md", ".txt"];
const PERMISSIONS = ["L1", "L2", "L3"];
const KNOWLEDGE_BASES: { value: string; label: string }[] = [
  { value: "qa", label: "制度知识库" },
  { value: "ticket", label: "工单知识库" },
  { value: "sales", label: "营销知识库" },
  { value: "ops", label: "运维知识库" },
];

const KB_TAGS: Record<string, string[]> = {
  qa: ["差旅交通", "奖金激励", "入职须知", "通知文件", "业务规则"],
  ticket: ["网络故障", "账号权限", "硬件报修", "软件安装", "系统异常"],
  sales: ["产品报价", "竞品分析", "客户案例", "营销话术", "投放策略"],
  ops: ["监控告警", "部署变更", "备份恢复", "日志排查", "性能优化"],
};

export default function UploadZone({ onSuccess }: { onSuccess: () => void }) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [permissionLevel, setPermissionLevel] = useState("L1");
  const [knowledgeBase, setKnowledgeBase] = useState("qa");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagDropdownOpen, setTagDropdownOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const tagDropdownRef = useRef<HTMLDivElement>(null);

  const availableTags = KB_TAGS[knowledgeBase] || [];

  // Reset tags when KB changes
  useEffect(() => {
    setSelectedTags([]);
  }, [knowledgeBase]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (tagDropdownRef.current && !tagDropdownRef.current.contains(e.target as Node)) {
        setTagDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function toggleTag(tag: string) {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  }

  function removeTag(tag: string) {
    setSelectedTags((prev) => prev.filter((t) => t !== tag));
  }

  function validate(file: File): string | null {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!ALLOWED_EXTS.includes(ext)) {
      return `不支持的文件类型: ${ext}`;
    }
    return null;
  }

  async function handleFile(file: File) {
    const err = validate(file);
    if (err) {
      toast(err, "error");
      return;
    }
    setUploading(true);
    try {
      const result = await uploadDocument(
        file,
        permissionLevel,
        knowledgeBase,
        selectedTags.length > 0 ? selectedTags : undefined,
      );
      toast(result.message, "success");
      setSelectedTags([]);
      onSuccess();
    } catch {
      toast("上传失败", "error");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div
      className={`rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
        dragging ? "border-blue-400 bg-blue-50" : "border-gray-300 hover:border-gray-400"
      } ${uploading ? "pointer-events-none opacity-60" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
      }}
    >
      <input
        ref={fileRef}
        type="file"
        accept=".pdf,.docx,.md,.txt"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          if (fileRef.current) fileRef.current.value = "";
        }}
      />
      <p className="text-sm text-gray-600">
        {uploading ? "上传中..." : "拖拽文件到此处，或点击上传"}
      </p>
      <p className="mt-1 text-xs text-gray-400">支持 PDF、DOCX、MD、TXT 格式</p>

      {!uploading && (
        <>
          <div className="mt-3 flex items-center justify-center gap-4 flex-wrap">
            <select
              value={knowledgeBase}
              onChange={(e) => setKnowledgeBase(e.target.value)}
              className="rounded border border-gray-300 px-3 py-1.5 text-sm outline-none focus:border-blue-500"
            >
              {KNOWLEDGE_BASES.map((kb) => (
                <option key={kb.value} value={kb.value}>
                  {kb.label}
                </option>
              ))}
            </select>
            <select
              value={permissionLevel}
              onChange={(e) => setPermissionLevel(e.target.value)}
              className="rounded border border-gray-300 px-3 py-1.5 text-sm outline-none focus:border-blue-500"
            >
              {PERMISSIONS.map((pl) => (
                <option key={pl} value={pl}>
                  {pl} 权限
                </option>
              ))}
            </select>

            {/* Tag multi-select */}
            <div className="relative" ref={tagDropdownRef}>
              <button
                type="button"
                onClick={() => setTagDropdownOpen(!tagDropdownOpen)}
                className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:border-gray-400 outline-none min-w-[120px] text-left"
              >
                {selectedTags.length > 0
                  ? `已选 ${selectedTags.length} 个标签`
                  : "选择标签..."}
              </button>
              {tagDropdownOpen && (
                <div className="absolute z-10 mt-1 w-48 rounded border border-gray-200 bg-white shadow-lg max-h-48 overflow-y-auto">
                  {availableTags.map((tag) => (
                    <label
                      key={tag}
                      className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-gray-50 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selectedTags.includes(tag)}
                        onChange={() => toggleTag(tag)}
                        className="rounded accent-blue-600"
                      />
                      {tag}
                    </label>
                  ))}
                </div>
              )}
            </div>

            <button
              onClick={() => fileRef.current?.click()}
              className="rounded bg-blue-600 px-4 py-1.5 text-sm text-white hover:bg-blue-700"
            >
              选择文件
            </button>
          </div>

          {/* Selected tag chips */}
          {selectedTags.length > 0 && (
            <div className="mt-2 flex items-center justify-center gap-1.5 flex-wrap">
              {selectedTags.map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700"
                >
                  {tag}
                  <button
                    type="button"
                    onClick={() => removeTag(tag)}
                    className="ml-0.5 text-blue-400 hover:text-blue-600"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
