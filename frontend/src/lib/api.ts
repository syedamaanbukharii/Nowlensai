// Minimal typed API client for the NowLens backend.
// Reads the base URL from NEXT_PUBLIC_API_BASE_URL (default localhost:8000).

import type {
  ChatResponse,
  DocumentOut,
  DomainOut,
  IngestReport,
  JobOut,
  SearchResponse,
  TokenResponse,
  UserOut,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

const CSRF_COOKIE = "nowlens_csrf";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

// Authentication uses HttpOnly cookies set by the API, so the token is never
// exposed to JavaScript. For cookie-authenticated writes we echo the readable
// CSRF cookie back in the X-CSRF-Token header (double-submit).
function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${CSRF_COOKIE}=([^;]+)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export class ApiError extends Error {
  code: string;
  status: number;
  traceId: string | null;

  constructor(status: number, code: string, message: string, traceId: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.traceId = traceId;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const { method = "GET", body } = options;
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["content-type"] = "application/json";
  if (!SAFE_METHODS.has(method.toUpperCase())) {
    const csrf = getCsrfToken();
    if (csrf) headers["x-csrf-token"] = csrf;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      // Send/receive the auth + CSRF cookies (cross-origin needs API CORS
      // allow-credentials + a non-Lax SameSite, which the backend supports).
      credentials: "include",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "network_error", `Couldn't reach the API at ${API_BASE}.`, null);
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const code = data?.code ?? "error";
    const message = data?.message ?? `Request failed (${res.status}).`;
    throw new ApiError(res.status, code, message, data?.trace_id ?? null);
  }
  return data as T;
}

// ---- auth ----
export const api = {
  register: (email: string, password: string) =>
    request<TokenResponse>("/api/v1/auth/register", {
      method: "POST",
      body: { email, password },
    }),

  login: (email: string, password: string) =>
    request<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    }),

  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),

  me: () => request<UserOut>("/api/v1/auth/me"),

  // ---- chat / search ----
  chat: (message: string, opts: { sessionId?: string | null; domains?: string[] } = {}) =>
    request<ChatResponse>("/api/v1/chat", {
      method: "POST",
      body: {
        message,
        session_id: opts.sessionId ?? null,
        domains: opts.domains ?? [],
        stream: false,
      },
    }),

  search: (query: string, domains: string[] = []) =>
    request<SearchResponse>("/api/v1/search", {
      method: "POST",
      body: { query, domains },
    }),

  // ---- domains ----
  domains: () => request<DomainOut[]>("/api/v1/domains"),

  // ---- admin ----
  ingest: (urls: string[], wait = true) =>
    request<{ reports: IngestReport[] } | { enqueued: string[]; job_ids: string[] }>(
      "/api/v1/ingest",
      { method: "POST", body: { urls, wait } },
    ),

  jobs: () => request<JobOut[]>("/api/v1/jobs"),

  documents: () => request<DocumentOut[]>("/api/v1/documents"),
};
