import { Loader2 } from "lucide-react";

/** A spinner with words, for a whole area that is loading. */
export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 p-8 label-caps">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}
