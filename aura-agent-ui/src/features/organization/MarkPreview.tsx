import { previewMark } from "@/api/organization";
import { AuthImage } from "@/components/AuthImage";

import type { BrandForm } from "./schema";

/** The bottom of a Letter page with the mark at the bottom right, drawn by the
 * server with the code that marks every cleaned PDF. Cached per brand. */
export function MarkPreview({ brand, compact = false }: { brand: BrandForm; compact?: boolean }) {
  return (
    <AuthImage
      queryKey={["mark-preview", JSON.stringify(brand)]}
      load={(signal) => previewMark(brand, signal)}
      alt="The mark as it will print on a page"
      compact={compact}
      className={compact ? "min-h-12" : "min-h-24"}
    />
  );
}
