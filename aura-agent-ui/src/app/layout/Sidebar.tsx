import { Building2, House, Layers, LogOut, PanelLeft } from "lucide-react";
import { type ReactNode, useState } from "react";
import { NavLink } from "react-router";

import { BrandMark } from "@/components/BrandMark";
import { endSession } from "@/features/auth/session";
import { useSession } from "@/features/auth/useSession";
import { useJobCounts } from "@/features/home/hooks/useSummary";
import { cn } from "@/lib/cn";

const COLLAPSED_KEY = "aura-agent.rail-collapsed";

// Storage can be missing or refuse (a private window): the rail then opens expanded.
function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function writeCollapsed(collapsed: boolean) {
  try {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch {
    // Only the preference is lost.
  }
}

// Text that hides when the rail is collapsed, or under 820px where it always is.
const LABEL = "truncate group-data-[collapsed=true]/rail:hidden max-[820px]:hidden";

const item = "flex w-full items-center gap-[11px] rounded-[5px] px-[9px] py-2 font-mono text-[10.5px] font-medium " +
  "uppercase tracking-[0.14em] whitespace-nowrap text-fg-3 transition-colors duration-200 hover:text-fg-2";

function Group({ children }: { children: string }) {
  return <div className={cn("label-caps px-[9px] pt-[18px] pb-1.5", LABEL)}>{children}</div>;
}

export function Sidebar() {
  const session = useSession();
  const counts = useJobCounts();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const toReview = counts.data?.to_review ?? 0;

  const toggle = () => {
    writeCollapsed(!collapsed);
    setCollapsed(!collapsed);
  };

  // aria-label because the visible label is display:none while collapsed.
  const link = (to: string, label: string, Icon: typeof House, extra?: ReactNode, spoken = label) => (
    <NavLink to={to} end={to === "/"} title={label} aria-label={spoken}
      className={({ isActive }) => cn(item, isActive && "bg-raise-2 text-foreground hover:text-foreground")}>
      <Icon className="size-4 shrink-0" strokeWidth={1.5} aria-hidden />
      <span className={LABEL}>{label}</span>
      {extra}
    </NavLink>
  );

  return (
    <nav aria-label="Main" data-collapsed={collapsed}
      className="group/rail flex w-[216px] shrink-0 flex-col gap-0.5 overflow-hidden border-r border-line-2 px-3 py-4
        transition-[width] duration-300 ease-spring data-[collapsed=true]:w-[60px] max-[820px]:w-[60px]">
      <div className="flex items-center gap-2.5 px-1 pt-0.5 pb-[22px] whitespace-nowrap">
        <BrandMark className="h-6 w-7 shrink-0" />
        <span className={cn("font-mono text-[10px] font-medium uppercase tracking-[0.22em] text-fg-2", LABEL)}>
          Aura Agent
        </span>
      </div>
      {link("/", "Home", House)}
      <Group>Capabilities</Group>
      {link("/jobs", "Unbranding", Layers, toReview > 0 && (
        <span className={cn("ml-auto font-mono tracking-normal text-gold-text tabular-nums", LABEL)}>{toReview}</span>
      ), toReview > 0 ? `Unbranding, ${toReview} to review` : "Unbranding")}
      <Group>Settings</Group>
      {link("/organization", "Organization", Building2)}
      <div className="mt-auto flex flex-col gap-0.5 border-t border-line-2 pt-2.5">
        <button type="button" className={cn(item, "max-[820px]:hidden")} onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}>
          <PanelLeft className="size-4 shrink-0" strokeWidth={1.5} aria-hidden />
          <span className={LABEL}>Collapse</span>
        </button>
        <button type="button" className={item} onClick={() => endSession()} aria-label="Sign out" title="Sign out">
          <LogOut className="size-4 shrink-0" strokeWidth={1.5} aria-hidden />
          <span className={LABEL}>Sign out</span>
        </button>
        {session?.name && <div className={cn("label-caps truncate px-[9px] pt-1", LABEL)}>{session.name}</div>}
      </div>
    </nav>
  );
}
