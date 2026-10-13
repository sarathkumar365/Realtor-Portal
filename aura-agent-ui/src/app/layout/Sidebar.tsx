import { Building2, FileStack } from "lucide-react";
import { NavLink } from "react-router";

import { BrandMark } from "@/components/BrandMark";
import { cn } from "@/lib/cn";

// Each area of the app is one entry; a new capability adds its own.
const NAV = [
  { to: "/jobs", label: "Unbrander jobs", icon: FileStack },
  { to: "/organization", label: "Organization", icon: Building2 },
];

export function Sidebar() {
  return (
    <nav aria-label="Main" className="flex w-60 shrink-0 flex-col gap-1 bg-sidebar p-4 text-sidebar-foreground">
      <div className="mb-6 flex items-center gap-2 px-2">
        <BrandMark className="h-6" />
        <span className="font-bold tracking-wide">Aura Agent</span>
      </div>
      {NAV.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            cn("flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold",
              isActive ? "bg-white/10 text-white" : "text-sidebar-foreground/70 hover:bg-white/5")}
        >
          <Icon className="size-4" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
