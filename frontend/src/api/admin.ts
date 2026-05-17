import apiClient, { handleApiError } from "./client";
import type {
  AdminSettings,
  UpdateSettingsRequest,
  LogListResponse,
  LogFilters,
  Metrics,
} from "../types/admin";

export async function getSettings(): Promise<AdminSettings> {
  try {
    const resp = await apiClient.get<AdminSettings>("/admin/settings");
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}

export async function updateSettings(
  body: UpdateSettingsRequest,
): Promise<AdminSettings> {
  try {
    const resp = await apiClient.put<AdminSettings>("/admin/settings", body);
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}

export async function getLogs(
  filters: LogFilters,
): Promise<LogListResponse> {
  try {
    const resp = await apiClient.get<LogListResponse>("/admin/logs", {
      params: filters,
    });
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}

export async function getMetrics(): Promise<Metrics> {
  try {
    const resp = await apiClient.get<Metrics>("/admin/metrics");
    return resp.data;
  } catch (error) {
    return handleApiError(error);
  }
}
