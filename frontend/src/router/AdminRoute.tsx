import { Outlet } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";

export default function AdminRoute() {
  const role = useAuthStore((s) => s.user?.role);

  if (role !== "admin") {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center">
          <p className="text-6xl font-bold text-gray-200">403</p>
          <p className="mt-4 text-lg text-gray-600">暂无权限访问此页面</p>
          <p className="text-sm text-gray-400">需要管理员权限</p>
        </div>
      </div>
    );
  }

  return <Outlet />;
}
