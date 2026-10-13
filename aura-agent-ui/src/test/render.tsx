import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";

import { connectClient } from "@/app/connectClient";
import { makeQueryClient } from "@/app/queryClient";
import { Toaster } from "@/components/ui/sonner";
import { routes } from "@/app/routes";
import { startSession } from "@/features/auth/session";

import { ADMIN_TOKEN } from "./msw/handlers";

/** The whole app at `path`, as it runs in the browser but on a memory router. */
export function renderApp(path: string, { signedIn = true } = {}) {
  connectClient();
  if (signedIn) startSession({ token: ADMIN_TOKEN, user: "admin", name: "Sudhanshu" });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = makeQueryClient();
  queryClient.setDefaultOptions({ queries: { ...queryClient.getDefaultOptions().queries, retryDelay: 0 } });
  const user = userEvent.setup();
  return { user, router, ...render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>,
  ) };
}
