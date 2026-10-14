import type { Blocker } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";

export function LeaveDialog({ blocker, what }: { blocker: Blocker; what: string }) {
  return (
    <ConfirmDialog
      open={blocker.state === "blocked"}
      title="Leave without saving?"
      description={`Your changes to ${what} will be lost.`}
      confirmLabel="Leave"
      cancelLabel="Stay"
      onConfirm={() => blocker.proceed?.()}
      onCancel={() => blocker.reset?.()}
    />
  );
}
