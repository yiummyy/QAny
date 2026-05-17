import LoginForm from "../components/auth/LoginForm";

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-lg">
        <h1 className="mb-1 text-center text-2xl font-bold text-gray-900">
          企业知识库问答
        </h1>
        <p className="mb-6 text-center text-sm text-gray-500">请登录以继续</p>
        <LoginForm />
      </div>
    </div>
  );
}
