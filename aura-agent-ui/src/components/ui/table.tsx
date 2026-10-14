import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <div className="overflow-x-auto">
      <table className={cn("w-full text-left", className)} {...props} />
    </div>
  );
}

export function TableHead({ className, ...props }: ComponentProps<"thead">) {
  return <thead className={cn("border-b border-line-2 [&_th]:label-caps", className)} {...props} />;
}

export function TableBody(props: ComponentProps<"tbody">) {
  return <tbody {...props} />;
}

export function TableRow({ className, ...props }: ComponentProps<"tr">) {
  return <tr className={cn("border-b border-line-2 transition-colors last:border-0 hover:bg-raise", className)} {...props} />;
}

export function TableHeader({ className, ...props }: ComponentProps<"th">) {
  return <th scope="col" className={cn("px-1 py-2.5 font-medium", className)} {...props} />;
}

export function TableCell({ className, ...props }: ComponentProps<"td">) {
  return <td className={cn("px-1 py-3 align-top", className)} {...props} />;
}
