import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "../stores/authStore";

export class ApiError extends Error {
  constructor(
    public code: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 30000,
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // 默认设置为 application/json，但如果是 FormData 则让浏览器自动设置
  if (config.data instanceof FormData) {
    delete config.headers["Content-Type"];
  } else if (!config.headers["Content-Type"]) {
    config.headers["Content-Type"] = "application/json";
  }
  return config;
});

let isRefreshing = false;
let pendingQueue: Array<{
  resolve: (t: string) => void;
  reject: (e: unknown) => void;
}> = [];

function processQueue(token: string | null, error: unknown | null) {
  pendingQueue.forEach((p) => {
    if (token) p.resolve(token);
    else p.reject(error);
  });
  pendingQueue = [];
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    if (
      error.response?.status !== 401 ||
      originalRequest._retry ||
      originalRequest.url?.includes("/auth/login") ||
      originalRequest.url?.includes("/auth/refresh")
    ) {
      return Promise.reject(error);
    }

    const retryOriginalRequest = new Promise((resolve, reject) => {
      pendingQueue.push({
        resolve: (token: string) => {
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${token}`;
          }
          originalRequest._retry = true;
          resolve(apiClient(originalRequest));
        },
        reject,
      });
    });

    if (!isRefreshing) {
      isRefreshing = true;
      (async () => {
        try {
          const refreshToken = useAuthStore.getState().refreshToken;
          if (!refreshToken) throw new Error("No refresh token");

          const { data } = await axios.post(
            "/api/v1/auth/refresh",
            {},
            { headers: { Authorization: `Bearer ${refreshToken}` } },
          );

          useAuthStore.getState().setAccessToken(data.access_token);
          processQueue(data.access_token, null);
        } catch (refreshError) {
          processQueue(null, refreshError);
          useAuthStore.getState().logout();
          window.location.href = "/login";
        } finally {
          isRefreshing = false;
        }
      })();
    }

    return retryOriginalRequest;
  },
);

export async function handleApiError(error: unknown): Promise<never> {
  if (axios.isAxiosError(error) && error.response?.data) {
    const data = error.response.data as Record<string, unknown>;
    
    // Check if it's the new flattened error envelope (code and message at root)
    if (typeof data.code === "number" && typeof data.message === "string") {
      throw new ApiError(data.code, data.message);
    }
    
    // Fallback for older detail format just in case
    const detail = data.detail;
    if (typeof detail === "object" && detail !== null) {
      throw new ApiError(
        (detail as Record<string, unknown>).code as number,
        ((detail as Record<string, unknown>).message as string) ?? "未知错误",
      );
    }
  }
  throw new ApiError(50000, "网络请求失败，请检查连接");
}

export default apiClient;
