import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import type { JobAccepted } from "@/api/jobs";
import { UPLOAD_URL } from "@/api/jobs";
import { uploadForm, UploadCancelled } from "@/api/upload";

import { jobKeys } from "./useJobs";

export type UploadState =
  | { phase: "idle" }
  | { phase: "sending"; percent: number }
  | { phase: "failed"; error: unknown };

/** One upload at a time, with progress and Cancel. Warns before the tab closes
 * mid-upload: leaving would cancel it. */
export function useUpload() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<UploadState>({ phase: "idle" });
  const cancelRef = useRef<(() => void) | null>(null);
  const sending = state.phase === "sending";

  useEffect(() => {
    if (!sending) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [sending]);

  useEffect(() => () => cancelRef.current?.(), []);

  /** The accepted job, or what went wrong; neither when cancelled. */
  async function send(form: FormData): Promise<{ accepted?: JobAccepted; error?: unknown }> {
    if (sending) return {};
    setState({ phase: "sending", percent: 0 });
    const upload = uploadForm<JobAccepted>(UPLOAD_URL, form, (sent, total) =>
      setState({ phase: "sending", percent: Math.round((sent / total) * 100) }));
    cancelRef.current = upload.cancel;
    try {
      const accepted = await upload.done;
      setState({ phase: "idle" });
      await queryClient.invalidateQueries({ queryKey: jobKeys.all });
      return { accepted };
    } catch (error) {
      if (error instanceof UploadCancelled) {
        setState({ phase: "idle" });
        return {};
      }
      setState({ phase: "failed", error });
      return { error };
    } finally {
      cancelRef.current = null;
    }
  }

  return { state, send, cancel: () => cancelRef.current?.() };
}
