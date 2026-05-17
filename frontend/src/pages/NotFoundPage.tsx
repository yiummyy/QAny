import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <p className="text-6xl font-bold text-gray-200">404</p>
        <p className="mt-4 text-lg text-gray-600">页面不存在</p>
        <Link to="/" className="mt-4 inline-block text-blue-600 hover:underline text-sm">
          返回首页
        </Link>
      </div>
    </div>
  );
}
