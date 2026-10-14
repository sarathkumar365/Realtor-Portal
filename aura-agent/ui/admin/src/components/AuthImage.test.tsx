import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { ApiError } from "@/api/errors";
import { makeQueryClient } from "@/app/queryClient";

import { AuthImage } from "./AuthImage";

function view(key: string, load: () => Promise<Blob>) {
  return <AuthImage queryKey={["test", key]} load={load} alt="the page" />;
}

test("a new key that fails shows Retry, not the old image", async () => {
  const client = makeQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  const wrap = (node: React.ReactNode) => <QueryClientProvider client={client}>{node}</QueryClientProvider>;
  const { rerender } = render(wrap(view("first", async () => new Blob(["jpeg"]))));
  expect(await screen.findByAltText("the page")).toBeInTheDocument();
  rerender(wrap(view("second", async () => {
    throw new ApiError("server", "render failed", 500);
  })));
  expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  expect(screen.getByText("render failed")).toBeInTheDocument();
  expect(screen.queryByAltText("the page")).not.toBeInTheDocument();
});
