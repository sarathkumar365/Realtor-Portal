import { type ReactElement, cloneElement, useId } from "react";

import { Label } from "@/components/ui/label";

/** A label, one control and its error, wired for screen readers. The control is
 * given its id, aria-invalid and aria-describedby. */
export function FormField({ label, error, hint, children }: {
  label: string;
  error?: string;
  hint?: string;
  children: ReactElement<Record<string, unknown>>;
}) {
  const id = useId();
  const described = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {cloneElement(children, { id, "aria-invalid": error ? true : undefined, "aria-describedby": described })}
      {error ? (
        <p id={`${id}-error`} className="text-sm text-danger">{error}</p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-sm text-muted">{hint}</p>
      ) : null}
    </div>
  );
}
