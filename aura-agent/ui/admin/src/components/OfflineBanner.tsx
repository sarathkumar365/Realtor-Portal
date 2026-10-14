import { WifiOff } from "lucide-react";
import { useSyncExternalStore } from "react";

function subscribe(listener: () => void): () => void {
  window.addEventListener("online", listener);
  window.addEventListener("offline", listener);
  return () => {
    window.removeEventListener("online", listener);
    window.removeEventListener("offline", listener);
  };
}

/** A strip across the top while the browser says it is offline. */
export function OfflineBanner() {
  const online = useSyncExternalStore(subscribe, () => navigator.onLine);
  if (online) return null;
  return (
    <div role="status" className="flex items-center justify-center gap-2 border-b border-line bg-raise-2 px-4 py-2 font-mono text-[12px] uppercase tracking-[0.14em] text-foreground">
      <WifiOff className="size-4" aria-hidden />
      You are offline. Changes will not reach Aura until you are back.
    </div>
  );
}
