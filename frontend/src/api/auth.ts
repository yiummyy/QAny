import apiClient, { handleApiError } from "./client";
import type { LoginRequest, LoginResponse, UserProfile, RefreshResponse } from "../types/auth";

export async function login(body: LoginRequest): Promise<LoginResponse> {
  try {
    const resp = await apiClient.post<LoginResponse>("/auth/login", body);
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}

export async function refreshToken(): Promise<RefreshResponse> {
  try {
    const resp = await apiClient.post<RefreshResponse>("/auth/refresh");
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}

export async function logout(): Promise<void> {
  try {
    await apiClient.post("/auth/logout");
  } catch {
    // best-effort
  }
}

export async function getMe(): Promise<UserProfile> {
  try {
    const resp = await apiClient.get<UserProfile>("/auth/me");
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}
