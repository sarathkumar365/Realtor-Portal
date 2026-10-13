import { LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import { endSession } from "@/features/auth/session";
import { useSession } from "@/features/auth/useSession";

export function TopBar() {
  const session = useSession();
  return (
    <header className="flex h-14 shrink-0 items-center justify-end gap-3 border-b border-border bg-surface px-6">
      <span className="text-sm text-muted">{session?.name}</span>
      <Button variant="ghost" size="sm" onClick={() => endSession()}>
        <LogOut aria-hidden />
        Sign out
      </Button>
    </header>
  );
}
