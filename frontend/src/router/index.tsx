import { createBrowserRouter } from "react-router-dom";
import LoginPage from "../pages/LoginPage";
import ChatPage from "../pages/ChatPage";
import HistoryPage from "../pages/HistoryPage";
import KnowledgePage from "../pages/admin/KnowledgePage";
import SettingsPage from "../pages/admin/SettingsPage";
import LogsPage from "../pages/admin/LogsPage";
import NotFoundPage from "../pages/NotFoundPage";
import ProtectedRoute from "./ProtectedRoute";
import AdminRoute from "./AdminRoute";
import AppLayout from "../components/layout/AppLayout";
import AdminLayout from "../components/layout/AdminLayout";

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: "/", element: <ChatPage /> },
          { path: "/history", element: <HistoryPage /> },
        ],
      },
      {
        element: <AdminRoute />,
        children: [
          {
            element: <AdminLayout />,
            children: [
              { path: "/admin/knowledge", element: <KnowledgePage /> },
              { path: "/admin/settings", element: <SettingsPage /> },
              { path: "/admin/logs", element: <LogsPage /> },
            ],
          },
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]);
