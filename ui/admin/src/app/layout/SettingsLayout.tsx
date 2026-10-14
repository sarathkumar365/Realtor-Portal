import { NavLink, Outlet } from "react-router";

import { cn } from "@/lib/cn";

const SECTIONS = [
  { to: "/settings/organization", label: "Organization" },
  { to: "/settings/unbranding", label: "Unbranding" },
];

/** Settings is one place in the rail; its sections are tabs above the page. */
export function SettingsLayout() {
  return (
    <>
      <nav aria-label="Settings" className="mb-7 flex gap-1 border-b border-line-2">
        {SECTIONS.map(({ to, label }) => (
          <NavLink key={to} to={to}
            className={({ isActive }) => cn(
              "-mb-px border-b px-3 py-2.5 font-mono text-[11px] font-medium uppercase tracking-[0.14em] transition-colors",
              isActive ? "border-foreground text-foreground" : "border-transparent text-fg-2 hover:text-foreground")}>
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </>
  );
}
