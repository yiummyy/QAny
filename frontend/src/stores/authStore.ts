import { create } from "zustand";
import type { UserProfile } from "../types/auth";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: UserProfile | null;

  login: (tokens: {
    access_token: string;
    refresh_token: string;
    user: UserProfile;
  }) => void;
  logout: () => void;
  setAccessToken: (token: string) => void;
}

function loadUser(): UserProfile | null {
  try {
    const raw = localStorage.getItem("user");
    return raw ? (JSON.parse(raw) as UserProfile) : null;
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: localStorage.getItem("access_token"),
  refreshToken: localStorage.getItem("refresh_token"),
  user: loadUser(),

  login: ({ access_token, refresh_token, user }) => {
    localStorage.setItem("access_token", access_token);
    localStorage.setItem("refresh_token", refresh_token);
    localStorage.setItem("user", JSON.stringify(user));
    set({ accessToken: access_token, refreshToken: refresh_token, user });
  },

  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user");
    set({ accessToken: null, refreshToken: null, user: null });
  },

  setAccessToken: (token) => {
    localStorage.setItem("access_token", token);
    set({ accessToken: token });
  },
}));
