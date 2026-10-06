/**
 * Typed client for the TradeShield Flask API.
 * Every response is unwrapped from `{ "data": ... }`; errors arrive as
 * `{ "error": { "code", "message" } }` and are surfaced as ApiError.
 */

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5001/api";

export const TOKEN_KEY = "ts.token";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export interface ApiOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers ?? {}) };
  // Content-Type is only sent when there is a body: a Content-Type header makes
  // the request non-simple, so every GET would cost an extra CORS preflight.
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal ?? null,
      cache: "no-store",
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    // fetch() also rejects when the browser blocks a CORS preflight, so the
    // server being down and the origin being missing from CORS_ORIGINS look
    // identical from here -- mention both.
    throw new ApiError(
      0,
      "NETWORK_ERROR",
      `Cannot reach the TradeShield API at ${API_URL}. Check that the Flask server is running and that this page's origin (${typeof window === "undefined" ? "" : window.location.origin}) is listed in CORS_ORIGINS.`,
    );
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const envelope = (payload as { error?: { code?: string; message?: string } } | null)
      ?.error;
    const code = envelope?.code ?? "UNKNOWN";
    const message = envelope?.message ?? "The request failed.";
    if (response.status === 401 && token && !path.startsWith("/auth/")) {
      window.dispatchEvent(new CustomEvent("ts:unauthorized"));
    }
    throw new ApiError(response.status, code, message);
  }

  return (payload as { data: T } | null)?.data as T;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

export function errorCode(error: unknown): string {
  return error instanceof ApiError ? error.code : "UNKNOWN";
}
