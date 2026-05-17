import { useChatStore } from "../../stores/chatStore";

interface SidebarProps {
  onSelectSession?: (id: string) => void;
  activeId?: string | null;
  showNewButton?: boolean;
}

export default function Sidebar({
  onSelectSession,
  activeId,
  showNewButton = true,
}: SidebarProps) {
  const sessions = useChatStore((s) => s.sessions);
  const newSession = useChatStore((s) => s.newSession);
  const deleteSession = useChatStore((s) => s.deleteSession);
  const storeActiveId = useChatStore((s) => s.activeSessionId);

  const currentActive = activeId ?? storeActiveId;

  function handleNew() {
    const id = newSession();
    onSelectSession?.(id);
  }

  function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    deleteSession(id);
  }

  return (
    <aside className="flex h-full flex-col border-r bg-gray-50 w-56">
      {showNewButton && (
        <div className="p-3">
          <button
            onClick={handleNew}
            className="w-full rounded-lg border border-dashed border-gray-300 px-3 py-2 text-sm text-gray-600 hover:border-blue-400 hover:text-blue-600"
          >
            + 新建会话
          </button>
        </div>
      )}
      <div className="flex-1 overflow-y-auto px-2">
        {sessions.length === 0 && (
          <p className="px-3 py-6 text-center text-xs text-gray-400">暂无会话</p>
        )}
        {sessions.map((s) => (
          <div key={s.id} className="group relative">
            <button
              onClick={() => onSelectSession?.(s.id)}
              className={`mb-0.5 w-full truncate rounded-lg px-3 py-2 pr-8 text-left text-sm ${
                s.id === currentActive
                  ? "bg-blue-100 text-blue-800 font-medium"
                  : "text-gray-700 hover:bg-gray-100"
              }`}
            >
              {s.title}
            </button>
            <button
              onClick={(e) => handleDelete(e, s.id)}
              className="absolute right-2 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center justify-center w-5 h-5 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 text-xs"
              aria-label={`删除会话: ${s.title}`}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}
