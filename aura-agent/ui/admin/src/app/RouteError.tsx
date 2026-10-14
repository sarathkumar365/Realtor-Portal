import { useRouteError } from "react-router";

import { Button } from "@/components/ui/button";

/** A screen that threw while rendering: say so, never a white page. */
export function RouteError() {
  const error = useRouteError();
  console.error(error);
  return (
    <div role="alert" className="flex min-h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <p className="text-lg font-semibold">Something went wrong on this screen.</p>
      <p className="text-sm text-muted">Reloading usually fixes it. If it keeps happening, tell the developer what you clicked.</p>
      <Button onClick={() => window.location.reload()}>Reload</Button>
    </div>
  );
}
