import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";

import { Toaster } from "@/components/ui/sonner";

import { connectClient } from "./connectClient";
import { makeQueryClient } from "./queryClient";
import { routes } from "./routes";

connectClient();

const router = createBrowserRouter(routes);

export function App() {
  const [queryClient] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>
  );
}
