import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { API } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { serveOrganization } from "@/test/organization";
import { renderApp } from "@/test/render";

function serve(status: { worker: boolean; test_mode: boolean; drive: boolean; filing_problem: string | null }) {
  server.use(http.get(`${API}/admin/unbrander/status`, () => HttpResponse.json(status)));
}

function reading(label: string) {
  return screen.getByText(label, { selector: "dt" }).parentElement as HTMLElement;
}

test("the settings show the worker on, test mode and filing ready", async () => {
  serve({ worker: true, test_mode: true, drive: true, filing_problem: null });
  renderApp("/settings/unbranding");
  await screen.findByText("the worker that cleans uploaded PDFs");
  expect(within(reading("Unbranding")).getByText("On")).toBeInTheDocument();
  expect(within(reading("Test mode")).getByText("filing goes to Drive's Test folder")).toBeInTheDocument();
  expect(within(reading("Filing")).getByText("Ready")).toBeInTheDocument();
});

test("with the worker off, the settings say so and why filing is not possible", async () => {
  serve({ worker: false, test_mode: false, drive: true, filing_problem: "the Unbrander worker is switched off" });
  renderApp("/settings/unbranding");
  expect(await screen.findByText("the Unbrander worker is switched off")).toBeInTheDocument();
  expect(within(reading("Unbranding")).getByText("Off")).toBeInTheDocument();
  expect(within(reading("Filing")).getByText("Not possible")).toBeInTheDocument();
});

test("Settings is one item in the rail, with Organization and Unbranding as its tabs", async () => {
  serve({ worker: true, test_mode: false, drive: true, filing_problem: null });
  const { user, router } = renderApp("/");
  await user.click(await screen.findByRole("link", { name: "Settings" }));
  expect(router.state.location.pathname).toBe("/settings/organization");
  const tabs = screen.getByRole("navigation", { name: "Settings" });
  await user.click(within(tabs).getByRole("link", { name: "Unbranding" }));
  expect(await screen.findByText("the worker that cleans uploaded PDFs")).toBeInTheDocument();
});

test("an old Organization link still lands on its settings tab", async () => {
  serveOrganization();
  const { router } = renderApp("/organization/mark");
  await screen.findByRole("heading", { name: "Mark" });
  expect(router.state.location.pathname).toBe("/settings/organization/mark");
});
