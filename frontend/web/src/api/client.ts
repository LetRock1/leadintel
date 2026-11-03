import { createHttpClient } from "@xedu/shared/lib";

const TOKEN_KEY = "xe-learner-token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: the session lasts until the tab closes */
  }
}

let onSignedOut: () => void = () => {};

/** The app registers what happens when the server says the session has ended. */
export function setSignedOutHandler(fn: () => void): void {
  onSignedOut = fn;
}

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

/** The learner API: every path is relative to /api/v1. */
export const api = createHttpClient({
  base: `${API_BASE}/api/v1`,
  token: getToken,
  onUnauthorized: () => {
    setToken(null);
    onSignedOut();
  },
});
