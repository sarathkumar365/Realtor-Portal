import { configureClient } from "@/api/client";
import { endSession, getSession } from "@/features/auth/session";

/** Gives api/ the session's token and ends the session on a 401. */
export function connectClient(): void {
  configureClient({
    token: () => getSession()?.token ?? null,
    onUnauthorized: () => endSession("Your session ended. Sign in again."),
  });
}
