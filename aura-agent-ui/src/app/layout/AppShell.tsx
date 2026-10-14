import { Outlet } from "react-router";

import { OfflineBanner } from "@/components/OfflineBanner";

import { Sidebar } from "./Sidebar";

/** A collapsible rail and one scrolling content column. */
export function AppShell() {
  return (
    <div className="flex h-full">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <OfflineBanner />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1120px] px-7 pt-[30px] pb-[72px] max-[820px]:px-4 max-[820px]:pt-[22px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
