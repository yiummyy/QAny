import { NavLink, useNavigate } from "react-router-dom";

const LINKS = [
  { to: "/admin/knowledge", label: "知识库", icon: "📚" },
  { to: "/admin/settings", label: "系统配置", icon: "⚙️" },
  { to: "/admin/logs", label: "问答日志", icon: "📋" },
];

export default function AdminNav() {
  const navigate = useNavigate();

  return (
    <aside className="w-64 flex flex-col bg-white border-r h-full">
      <div className="p-6">
        <h2 className="text-xl font-bold text-gray-800">管理后台</h2>
      </div>
      <nav className="flex-1 px-4 space-y-2">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-blue-50 text-blue-700"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              }`
            }
          >
            <span className="text-lg">{link.icon}</span>
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="p-4 border-t">
        <button
          onClick={() => navigate("/")}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors"
        >
          <span>⬅️</span>
          返回主页面
        </button>
      </div>
    </aside>
  );
}
