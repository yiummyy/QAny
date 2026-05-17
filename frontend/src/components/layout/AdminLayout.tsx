import { Outlet } from "react-router-dom";
import AdminNav from "../admin/AdminNav";

export default function AdminLayout() {
  return (
    <div className="flex h-screen bg-gray-50">
      <AdminNav />
      <main className="flex-1 overflow-auto bg-white m-4 rounded-lg shadow-sm border border-gray-100">
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
