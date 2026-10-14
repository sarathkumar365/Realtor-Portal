/** Every way a call to Aura can fail, as the screens need to tell them apart. */
export type ApiErrorKind =
  | "offline" // no response at all: network down, server down, or CORS refused
  | "timeout"
  | "unauthorized" // 401: the session ended
  | "forbidden" // 403: signed in, but not an admin
  | "not_found"
  | "too_large" // 413
  | "invalid" // 422: see `fields`
  | "rate_limited" // 429
  | "server"; // 5xx, or a response that is not what was expected

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  /** For `invalid`: the message for each field the server named. */
  readonly fields: Record<string, string>;

  constructor(kind: ApiErrorKind, message: string, status: number | null = null,
              fields: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.fields = fields;
  }
}

/** Worth trying again without the user changing anything. */
export function isRetryable(error: unknown): boolean {
  return error instanceof ApiError
    && ["offline", "timeout", "server", "rate_limited"].includes(error.kind);
}

const KIND_BY_STATUS: Record<number, ApiErrorKind> = {
  401: "unauthorized", 403: "forbidden", 404: "not_found", 413: "too_large",
  422: "invalid", 429: "rate_limited",
};

/** FastAPI's `detail`: a string, or a list of validation errors with a `loc`. */
export function errorFromResponse(status: number, body: unknown): ApiError {
  const kind = KIND_BY_STATUS[status] ?? "server";
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (Array.isArray(detail)) {
    const fields: Record<string, string> = {};
    for (const item of detail as { loc?: unknown[]; msg?: string }[]) {
      // loc is ["body", "mark_words", 0, "text"]: the field is the path after "body".
      const path = (item.loc ?? []).filter((part) => part !== "body").join(".");
      if (path && item.msg && !(path in fields)) fields[path] = item.msg;
    }
    const first = (detail[0] as { msg?: string } | undefined)?.msg;
    return new ApiError(kind, first ?? "The request was not valid", status, fields);
  }
  if (typeof detail === "string" && detail) return new ApiError(kind, detail, status);
  return new ApiError(kind, DEFAULT_MESSAGE[kind], status);
}

export const DEFAULT_MESSAGE: Record<ApiErrorKind, string> = {
  offline: "Cannot reach Aura. Check your connection and try again.",
  timeout: "Aura took too long to answer. Try again.",
  unauthorized: "Your session ended. Sign in again.",
  forbidden: "Admins only.",
  not_found: "Not found.",
  too_large: "The file is too large.",
  invalid: "The request was not valid.",
  rate_limited: "Too many attempts. Wait a moment and try again.",
  server: "Aura had a problem. Try again in a moment.",
};
