import { useState } from "react";
import { Outlet } from "react-router-dom";
import Header from "./Header";

export default function AppLayout() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="flex h-screen flex-col">
      <Header />
      <button
        onClick={() => setMobileNavOpen(!mobileNavOpen)}
        className="flex items-center gap-1 border-b px-3 py-2 text-sm text-gray-600 md:hidden"
        aria-label="切换导航"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
        菜单
      </button>
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
