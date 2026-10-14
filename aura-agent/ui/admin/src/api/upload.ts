/**
 * Uploads with XMLHttpRequest, not fetch: fetch cannot report upload progress, and
 * a 50 MB brochure on office Wi-Fi needs a progress bar and a Cancel button.
 */
import { sessionEnded, sessionToken } from "./client";
import { ApiError, DEFAULT_MESSAGE, errorFromResponse } from "./errors";

export interface UploadHandle<T> {
  done: Promise<T>;
  cancel: () => void;
}

export class UploadCancelled extends Error {}

const UPLOAD_TIMEOUT_MS = 10 * 60_000;

export function uploadForm<T>(url: string, form: FormData,
                              onProgress: (sent: number, total: number) => void): UploadHandle<T> {
  const xhr = new XMLHttpRequest();
  const done = new Promise<T>((resolve, reject) => {
    xhr.open("POST", url);
    const token = sessionToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.timeout = UPLOAD_TIMEOUT_MS;
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded, event.total);
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // not JSON: handled below
      }
      if (xhr.status >= 200 && xhr.status < 300 && body) {
        resolve(body as T);
        return;
      }
      const error = xhr.status >= 200 && xhr.status < 300
        ? new ApiError("server", "Aura answered with something that is not JSON", xhr.status)
        : errorFromResponse(xhr.status, body);
      if (error.kind === "unauthorized") sessionEnded();
      reject(error);
    };
    xhr.onerror = () => reject(new ApiError("offline", DEFAULT_MESSAGE.offline));
    xhr.ontimeout = () => reject(new ApiError("timeout", "The upload took too long. Try again."));
    xhr.onabort = () => reject(new UploadCancelled("cancelled"));
    xhr.send(form);
  });
  return { done, cancel: () => xhr.abort() };
}
