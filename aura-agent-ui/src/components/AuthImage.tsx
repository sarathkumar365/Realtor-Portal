import { useQuery } from "@tanstack/react-query";
import { ImageOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ApiError } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { limiter } from "@/lib/concurrency";
import { cn } from "@/lib/cn";

// Shared by every AuthImage on the page: the server renders each image on a thread.
const queue = limiter(4);

/** An image that needs the bearer token, so it cannot be a plain <img src>. Loads
 * when scrolled near, at most 4 at a time; a skeleton until then, a placeholder
 * with Retry if it fails. `queryKey` caches it: the same key is never fetched twice. */
export function AuthImage({ queryKey, load, alt, className }: {
  queryKey: readonly unknown[];
  load: (signal: AbortSignal) => Promise<Blob>;
  alt: string;
  className?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const visible = useVisible(box);
  const image = useQuery({
    queryKey,
    queryFn: ({ signal }) => queue(() => load(signal)),
    enabled: visible,
    staleTime: Infinity,
  });
  const url = useObjectUrl(image.data);

  return (
    <div ref={box} className={cn("relative min-h-40", className)}>
      {url ? (
        <img src={url} alt={alt} className="h-auto w-full rounded-lg border border-border bg-white" />
      ) : image.isError ? (
        <div role="alert" className="flex h-full min-h-40 flex-col items-center justify-center gap-2 rounded-lg border border-border bg-surface p-4 text-center text-sm text-muted">
          <ImageOff className="size-5" aria-hidden />
          {image.error instanceof ApiError ? image.error.message : "Could not load the image."}
          <Button variant="secondary" size="sm" onClick={() => image.refetch()}>Retry</Button>
        </div>
      ) : (
        <Skeleton className="absolute inset-0" />
      )}
    </div>
  );
}

function useVisible(element: React.RefObject<HTMLElement | null>): boolean {
  const [visible, setVisible] = useState(typeof IntersectionObserver === "undefined");
  useEffect(() => {
    if (visible || !element.current) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry?.isIntersecting) setVisible(true);
    }, { rootMargin: "400px" });
    observer.observe(element.current);
    return () => observer.disconnect();
  }, [element, visible]);
  return visible;
}

/** The object URL of `blob`, or null while there is none. Only a URL made from the
 * current blob is returned: after the key changes, the old one is revoked and must
 * not be shown, or the <img> breaks and an error never gets its Retry. */
function useObjectUrl(blob: Blob | undefined): string | null {
  const [current, setCurrent] = useState<{ blob: Blob; url: string } | null>(null);
  useEffect(() => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    // Created and revoked in the same effect: a URL made during render would be
    // revoked by StrictMode's re-run while the <img> still points at it.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCurrent({ blob, url });
    return () => URL.revokeObjectURL(url);
  }, [blob]);
  return current && current.blob === blob ? current.url : null;
}
