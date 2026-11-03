/**
 * A small JSON client for the backend API. Both apps call relative URLs (/api/v1/...); in development Vite proxies
 * them to the backend on port 8000, so the browser never needs cross-origin requests.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export type Query = Record<string, string | number | boolean | null | undefined>;

export interface HttpClientOptions {
  base: string;
  /** Returns the bearer token to send, if any. */
  token?: () => string | null;
  /** Called on 401: the session has ended (the app signs the person out). */
  onUnauthorized?: () => void;
}

function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `${path}${path.includes("?") ? "&" : "?"}${s}` : path;
}

function messageOf(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
  }
  if (status === 0) return "The server cannot be reached. Check that the backend is running.";
  if (status >= 500) return "Something went wrong on the server. Try again in a moment.";
  return `The request failed (${status}).`;
}

export function createHttpClient(opts: HttpClientOptions) {
  async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    const token = opts.token?.();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    let res: Response;
    try {
      res = await fetch(opts.base + withQuery(path, query), {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError(0, messageOf(0, null));
    }
    const type = res.headers.get("content-type") ?? "";
    const data: unknown = type.includes("application/json") ? await res.json().catch(() => null) : await res.text();
    if (!res.ok) {
      if (res.status === 401 && token) opts.onUnauthorized?.();
      throw new ApiError(res.status, messageOf(res.status, data), data);
    }
    return data as T;
  }

  return {
    get: <T>(path: string, query?: Query) => request<T>("GET", path, undefined, query),
    post: <T>(path: string, body?: unknown, query?: Query) => request<T>("POST", path, body ?? {}, query),
    put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body ?? {}),
    del: <T>(path: string) => request<T>("DELETE", path),
    /** Download a file response (for example a CSV export) and save it in the browser. */
    async download(path: string, fallbackName: string): Promise<void> {
      const token = opts.token?.();
      const res = await fetch(opts.base + path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new ApiError(res.status, messageOf(res.status, await res.json().catch(() => null)));
      const blob = await res.blob();
      const cd = res.headers.get("content-disposition") ?? "";
      const name = /filename=([^;]+)/.exec(cd)?.[1]?.replace(/"/g, "") ?? fallbackName;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    },
  };
}

export type HttpClient = ReturnType<typeof createHttpClient>;

/** A readable message for any error thrown by a request. */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong.";
}
