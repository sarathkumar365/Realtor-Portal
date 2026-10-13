import { Outlet } from "react-router";

import { OfflineBanner } from "@/components/OfflineBanner";

import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

/** Desktop-first: a fixed sidebar and a scrolling main area. */
export function AppShell() {
  return (
    <div className="flex h-full">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <OfflineBanner />
        <TopBar />
        <main className="flex-1 overflow-y-auto p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
