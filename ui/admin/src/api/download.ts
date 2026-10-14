import { send } from "./client";

const REVOKE_AFTER_MS = 60_000;

/** Fetches with the bearer header (a plain link cannot send it) and saves the file
 * under the name the server gives in Content-Disposition. Throws ApiError. */
export async function download(path: string, fallbackName: string): Promise<void> {
  const response = await send(path, { timeoutMs: 120_000 });
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = filenameOf(response.headers.get("Content-Disposition")) ?? fallbackName;
    document.body.append(link);
    link.click();
    link.remove();
  } finally {
    // Not at once: Safari and Firefox read the blob after click() returns, and a
    // revoked URL fails the save. A minute is ample for a PDF held in memory.
    setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS);
  }
}

export function filenameOf(disposition: string | null): string | null {
  const match = disposition?.match(/filename="([^"]+)"/);
  return match?.[1] ?? null;
}
