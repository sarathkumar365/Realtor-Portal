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
export function AuthImage({ queryKey, load, alt, className, compact = false, fit = false }: {
  queryKey: readonly unknown[];
  load: (signal: AbortSignal) => Promise<Blob>;
  alt: string;
  className?: string;
  /** A thumbnail, often inside a link: no minimum height, and a failure is an
   * icon with the reason as its tooltip. No Retry button, which a link cannot
   * hold; the full-size image beyond the link has one. */
  compact?: boolean;
  /** Fill the box and keep the whole page in view (object-fit: contain): for a
   * page shown to a fixed height. */
  fit?: boolean;
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
    <div ref={box} className={cn("relative", !compact && "min-h-40", className)}>
      {url ? (
        <img src={url} alt={alt}
          className={fit ? "h-full w-full object-contain" : "h-auto w-full rounded-[2px] bg-white"} />
      ) : image.isError && compact ? (
        <span role="img" aria-label={`${alt}: could not load`}
          title={image.error instanceof ApiError ? image.error.message : "Could not load the image."}
          className="absolute inset-0 grid place-items-center rounded-[2px] border border-line bg-raise text-fg-3">
          <ImageOff className="size-4" aria-hidden />
        </span>
      ) : image.isError ? (
        <div role="alert" className="flex h-full min-h-40 flex-col items-center justify-center gap-2 rounded-[10px] border border-line-2 bg-raise p-4 text-center text-sm text-muted">
          <ImageOff className="size-5" aria-hidden />
          {image.error instanceof ApiError ? image.error.message : "Could not load the image."}
          <Button variant="quiet" size="sm" onClick={() => image.refetch()}>Retry</Button>
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
