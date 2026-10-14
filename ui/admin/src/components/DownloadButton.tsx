import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/errors";
import { Button } from "@/components/ui/button";

/** Runs a download and says so when it fails; disabled while it runs, so a slow
 * file is not fetched twice. */
export function DownloadButton({ onDownload, label = "Download", size = "sm" }: {
  onDownload: () => Promise<void>;
  label?: string;
  size?: "sm" | "md";
}) {
  const [pending, setPending] = useState(false);
  async function run() {
    setPending(true);
    try {
      await onDownload();
    } catch (error) {
      toast.error(`Download failed: ${error instanceof ApiError ? error.message : "try again"}`);
    } finally {
      setPending(false);
    }
  }
  return (
    <Button variant="quiet" size={size} onClick={run} disabled={pending}>
      {pending ? <Loader2 className="animate-spin" aria-hidden /> : <Download aria-hidden />}
      {pending ? "Downloading" : label}
    </Button>
  );
}
