import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** How a state looks. The feature maps its own statuses onto these. */
export type StatusKind = "review" | "working" | "done" | "failed" | "idle" | "live";

const GLYPH: Record<StatusKind, string> = {
  review: "rounded-full border-gold bg-gold",
  working: "size-2 rounded-full border-fg-2 border-t-transparent animate-spin",
  done: "rounded-full border-fg-2 bg-fg-2",
  failed: "rounded-[1px] border-current",
  idle: "rounded-full border-current",
  live: "rounded-full border-foreground bg-foreground",
};

const TEXT: Record<StatusKind, string> = {
  review: "text-gold-text",
  working: "text-fg-2",
  done: "text-fg-2",
  failed: "text-foreground",
  idle: "text-fg-3",
  live: "text-foreground",
};

/** A state as a glyph and a word, never a coloured pill. Gold only for "review". */
export function StatusMark({ kind, children, className }: { kind: StatusKind; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-[7px] font-mono text-[10px] font-medium uppercase tracking-[0.16em] whitespace-nowrap",
      TEXT[kind], className)}>
      <span aria-hidden className={cn("size-1.5 shrink-0 border", GLYPH[kind])} />
      {children}
    </span>
  );
}
