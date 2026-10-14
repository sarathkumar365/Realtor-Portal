import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-[4px] font-mono text-[10.5px] font-medium uppercase tracking-[0.14em] whitespace-nowrap " +
    "transition-[color,background-color,border-color,opacity,transform] duration-300 ease-spring " +
    "disabled:pointer-events-none disabled:opacity-40 [&_svg]:size-3.5 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-foreground text-background hover:-translate-y-px",
        quiet: "border border-line text-fg-2 hover:text-foreground",
        bare: "text-fg-3 hover:text-foreground",
        danger: "bg-danger text-white hover:opacity-90",
      },
      size: {
        sm: "h-7 px-2.5",
        md: "h-[34px] px-3.5",
        lg: "h-10 px-5",
        icon: "size-8 tracking-normal",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

type ButtonProps = ComponentProps<"button"> & VariantProps<typeof buttonVariants> & {
  /** Render the child (a link) with the button's look. */
  asChild?: boolean;
};

export function Button({ className, variant, size, asChild = false, type, ...props }: ButtonProps) {
  const Component = asChild ? Slot.Root : "button";
  return (
    <Component
      // A button inside a form submits by default; ours do not unless asked.
      type={asChild ? undefined : (type ?? "button")}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}
