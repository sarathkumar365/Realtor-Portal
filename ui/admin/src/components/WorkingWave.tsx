import type { CSSProperties } from "react";

import { cn } from "@/lib/cn";

// One wavelength (12px) of the line, used as a mask so the colour stays a token.
const WAVE = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='M0 4 Q3 0.8 6 4 T12 4' fill='none' stroke='black' stroke-width='2'/%3E%3C/svg%3E")`;

const wave: CSSProperties = {
  maskImage: WAVE, WebkitMaskImage: WAVE,
  maskRepeat: "repeat-x", WebkitMaskRepeat: "repeat-x",
  maskPosition: "0 center", WebkitMaskPosition: "0 center",
  animation: "wave-drift 0.9s linear infinite",
};

// The ring: a circle of radius 3.6 that ripples eight times around, drawn once.
const RING = Array.from({ length: 73 }, (_, step) => {
  const angle = (step / 72) * 2 * Math.PI;
  const radius = 3.6 + 0.7 * Math.sin(angle * 8);
  return `${step ? "L" : "M"}${(5 + radius * Math.cos(angle)).toFixed(2)} ${(5 + radius * Math.sin(angle)).toFixed(2)}`;
}).join(" ");

/**
 * The agent is working: a wavy line that keeps moving, after Android's wavy
 * progress. `bar` with a `value` (0 to 1) fills to it; without one, a short wave
 * travels the track. `ring` sits in a status mark where a dot would.
 */
export function WorkingWave({ form, value, label, className }: {
  form: "bar" | "ring";
  value?: number;
  /** What is being waited for, for screen readers: "Floor plans: 1 of 3 documents done". */
  label?: string;
  className?: string;
}) {
  if (form === "ring") {
    return (
      <svg viewBox="0 0 10 10" aria-hidden className={cn("size-2.5 shrink-0 animate-[spin_2.4s_linear_infinite] text-state-working", className)}>
        <path d={RING} fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      </svg>
    );
  }
  const known = value !== undefined;
  const percent = known ? Math.round(Math.min(Math.max(value, 0), 1) * 100) : undefined;
  return (
    <div role="progressbar" aria-label={label} aria-valuemin={known ? 0 : undefined} aria-valuemax={known ? 100 : undefined}
      aria-valuenow={percent} className={cn("relative h-2 w-full overflow-hidden", className)}>
      {/* The flat track: what is still to do. It starts after the wave, as on Android. */}
      <div className="absolute right-0 top-1/2 h-0.5 -translate-y-1/2 rounded-full bg-line transition-[left] duration-700 ease-spring"
        style={{ left: known ? `calc(${percent}% + 4px)` : 0 }} />
      {known ? (
        <div className="absolute inset-y-0 left-0 bg-state-working transition-[width] duration-700 ease-spring"
          style={{ ...wave, width: `${percent}%` }} />
      ) : (
        <div className="absolute inset-y-0 w-[30%] bg-state-working"
          style={{ ...wave, animation: `${wave.animation}, wave-travel 1.8s ease-in-out infinite` }} />
      )}
    </div>
  );
}
