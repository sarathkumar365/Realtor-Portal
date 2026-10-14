import type { ComponentProps } from "react";

import { Input } from "@/components/ui/input";

const HEX = /^#[0-9a-fA-F]{6}$/;

/** A colour as `#RRGGBB`: a swatch picker beside the hex text, kept in step. Put
 * it inside FormField like an Input; the id and aria props go to the text box. */
export function ColourField({ value, onChange, onBlur, name, ...aria }: {
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  name?: string;
} & Pick<ComponentProps<"input">, "id" | "aria-invalid" | "aria-describedby">) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        aria-label="Pick a colour"
        tabIndex={-1}
        value={HEX.test(value) ? value : "#000000"}
        onChange={(event) => onChange(event.target.value.toUpperCase())}
        className="size-[38px] shrink-0 cursor-pointer rounded-[4px] border border-line bg-raise p-1"
      />
      <Input name={name} value={value} onBlur={onBlur} spellCheck={false} maxLength={7} className="font-mono"
        onChange={(event) => onChange(event.target.value)} {...aria} />
    </div>
  );
}
