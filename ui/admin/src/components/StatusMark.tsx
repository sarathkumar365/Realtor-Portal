import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

import { WorkingWave } from "./WorkingWave";

/** How a state looks. The feature maps its own statuses onto these. */
export type StatusKind = "review" | "working" | "done" | "failed" | "idle" | "live";

// Working has no dot: it is the wave ring.
const GLYPH: Record<Exclude<StatusKind, "working">, string> = {
  review: "rounded-full border-gold bg-gold",
  done: "rounded-full border-current bg-current",
  failed: "rounded-[1px] border-current",
  idle: "rounded-full border-current",
  live: "rounded-full border-current bg-current",
};

const TEXT: Record<StatusKind, string> = {
  review: "text-gold-text",
  working: "text-state-working",
  done: "text-state-done",
  failed: "text-state-failed",
  idle: "text-state-waiting",
  live: "text-state-done",
};

/** A state as a glyph and a word in its state colour, never a coloured pill. The
 * shapes differ too, so the colour is never the only sign. Gold only for "review". */
export function StatusMark({ kind, children, className }: { kind: StatusKind; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-[7px] font-mono text-[11px] font-medium uppercase tracking-[0.16em] whitespace-nowrap",
      TEXT[kind], className)}>
      {kind === "working"
        ? <WorkingWave form="ring" />
        : <span aria-hidden className={cn("size-1.5 shrink-0 border", GLYPH[kind])} />}
      {children}
    </span>
  );
}
