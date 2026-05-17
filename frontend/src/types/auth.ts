export interface LoginRequest {
  username: string;
  password: string;
}

export interface UserProfile {
  user_id: string;
  username: string;
  role: "admin" | "employee" | "guest";
  permission_level: "L1" | "L2" | "L3";
  department: string | null;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: "Bearer";
  user: UserProfile;
}

export interface RefreshResponse {
  access_token: string;
  token_type: "Bearer";
}
