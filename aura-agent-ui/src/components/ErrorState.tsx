import { AlertTriangle, WifiOff } from "lucide-react";

import { ApiError, DEFAULT_MESSAGE } from "@/api/errors";
import { Button } from "@/components/ui/button";

/** What went wrong, in words, and a way to try again. For any failed load. */
export function ErrorState({ error, onRetry, title = "Could not load this" }: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  const offline = error instanceof ApiError && (error.kind === "offline" || error.kind === "timeout");
  const message = error instanceof ApiError ? error.message : DEFAULT_MESSAGE.server;
  const Icon = offline ? WifiOff : AlertTriangle;
  return (
    <div role="alert" className="flex flex-col items-center gap-3 rounded-xl border border-border bg-surface p-8 text-center">
      <Icon className="size-6 text-warning" aria-hidden />
      <p className="font-semibold">{title}</p>
      <p className="max-w-md text-sm text-muted">{message}</p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
