/**
 * The only code that calls fetch. Everything about talking to Aura lives here:
 * the base URL, the bearer header, the timeout, and turning every failure into an
 * ApiError a screen can act on. Swapping the backend touches api/ only.
 */
import { ApiError, DEFAULT_MESSAGE, errorFromResponse } from "./errors";

export const API_BASE = (import.meta.env.VITE_AURA_BASE ?? "http://localhost:8000").replace(/\/$/, "");
const DEFAULT_TIMEOUT_MS = 30_000;

interface ClientHooks {
  /** The session token, or null when signed out. */
  token: () => string | null;
  /** A 401 on a signed-in call: the session ended (expired, or the secret rotated). */
  onUnauthorized: () => void;
}

let hooks: ClientHooks = { token: () => null, onUnauthorized: () => {} };

/** Called once by the app shell; api/ never imports features/. */
export function configureClient(next: ClientHooks): void {
  hooks = next;
}

/** For the other transports in api/ (upload.ts uses XMLHttpRequest). */
export function sessionToken(): string | null {
  return hooks.token();
}

export function sessionEnded(): void {
  hooks.onUnauthorized();
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT";
  json?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Use this token instead of the session's: sign-in checks a token before keeping it. */
  token?: string;
}

/** The raw response, already checked: a non-2xx status throws an ApiError. */
export async function send(path: string, options: RequestOptions = {}): Promise<Response> {
  const token = options.token ?? hooks.token();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.json !== undefined) headers["Content-Type"] = "application/json";

  // Our own controller, not AbortSignal.timeout/any: it tells our timeout apart
  // from the caller's abort, and it works in every browser the admins use.
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const forward = () => controller.abort();
  options.signal?.addEventListener("abort", forward);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.json === undefined ? undefined : JSON.stringify(options.json),
      signal: controller.signal,
    });
  } catch (error) {
    if (timedOut) throw new ApiError("timeout", DEFAULT_MESSAGE.timeout);
    if (options.signal?.aborted) throw error; // the caller cancelled: not a failure to show
    throw new ApiError("offline", DEFAULT_MESSAGE.offline);
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", forward);
  }

  if (!response.ok) {
    const error = errorFromResponse(response.status, await response.json().catch(() => null));
    // Only a call made with the session's token ends the session: a wrong
    // password at sign-in is a 401 too.
    if (error.kind === "unauthorized" && token && options.token === undefined) {
      hooks.onUnauthorized();
    }
    throw error;
  }
  return response;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(path, options);
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError("server", "Aura answered with something that is not JSON", response.status);
  }
}
