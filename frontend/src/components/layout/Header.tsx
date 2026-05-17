import { useState, useRef, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuthStore } from "../../stores/authStore";
import { logout as apiLogout } from "../../api/auth";

export default function Header() {
  const user = useAuthStore((s) => s.user);
  const storeLogout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  async function handleLogout() {
    await apiLogout();
    storeLogout();
    navigate("/login");
  }

  const isAdmin = user?.role === "admin";

  return (
    <header className="flex h-14 items-center justify-between border-b bg-white px-4 shadow-sm">
      <Link to="/" className="text-lg font-bold text-blue-700">
        企业知识库
      </Link>

      <nav className="hidden items-center gap-4 text-sm md:flex">
        <Link
          to="/"
          className={`hover:text-blue-600 ${
            location.pathname === "/" ? "font-semibold text-blue-600" : "text-gray-600"
          }`}
        >
          对话
        </Link>
        <Link
          to="/history"
          className={`hover:text-blue-600 ${
            location.pathname === "/history" ? "font-semibold text-blue-600" : "text-gray-600"
          }`}
        >
          历史
        </Link>
        {isAdmin && (
          <Link
            to="/admin/knowledge"
            className={`hover:text-blue-600 ${
              location.pathname.startsWith("/admin") ? "font-semibold text-blue-600" : "text-gray-600"
            }`}
          >
            管理
          </Link>
        )}
      </nav>

      <div className="relative" ref={ref}>
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-2 rounded-lg px-2 py-1 text-sm text-gray-700 hover:bg-gray-100"
          aria-label="用户菜单"
          aria-expanded={open}
        >
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-xs font-medium text-blue-700">
            {user?.username?.charAt(0) ?? "?"}
          </span>
          <span className="hidden md:inline">{user?.username ?? "用户"}</span>
        </button>
        {open && (
          <div className="absolute right-0 top-full z-40 mt-1 w-36 rounded-lg border bg-white py-1 shadow-lg">
            <div className="border-b px-3 py-1.5 text-xs text-gray-400">
              {user?.role === "admin" ? "管理员" : user?.role === "employee" ? "员工" : "访客"}
            </div>
            <button
              onClick={handleLogout}
              className="w-full px-3 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50"
            >
              退出登录
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
