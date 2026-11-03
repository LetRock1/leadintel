import { createHttpClient } from "@xedu/shared/lib";

const TOKEN_KEY = "xe-crm-token";

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

/** The CRM API: every path is relative to /api/v1/crm. */
export const api = createHttpClient({
  base: "/api/v1/crm",
  token: getToken,
  onUnauthorized: () => {
    setToken(null);
    onSignedOut();
  },
});

/** The public part of the API (the course catalogue), shared with the website. */
export const publicApi = createHttpClient({ base: "/api/v1" });
