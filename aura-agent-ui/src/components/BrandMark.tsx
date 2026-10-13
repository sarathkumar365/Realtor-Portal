import { useId } from "react";

// The Aura Key "AK" monogram, from design_handoff_aura_key/README.md.
const PATH =
  "M270 95L150 660L70 660ZM300 50L555 660L445 660L262 118ZM244 428L280 428L280 464L244 464ZM292 428L328 428L328 464L292 464ZM244 476L280 476L280 512L244 512ZM292 476L328 476L328 512L292 512ZM600 40L710 40L710 660L600 660ZM710 250L880 40L965 40L710 375ZM710 455L782 278L975 660L860 660Z";

/** The gold monogram. Decorative: pair it with the product name in text. */
export function BrandMark({ className }: { className?: string }) {
  const gradient = useId();
  return (
    <svg viewBox="70 30 905 640" className={className} aria-hidden>
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#F0DCA9" />
          <stop offset="0.45" stopColor="#D3AE60" />
          <stop offset="1" stopColor="#9A7A3B" />
        </linearGradient>
      </defs>
      <path d={PATH} fill={`url(#${gradient})`} />
    </svg>
  );
}
