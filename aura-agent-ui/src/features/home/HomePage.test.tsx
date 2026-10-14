import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { server } from "@/test/msw/server";
import { API } from "@/test/msw/handlers";
import { renderApp } from "@/test/render";

const READY = {
  id: "job-1", status: "UNBRANDED", uploader: "admin", instructions: null, project: "Bright Side Towns",
  builder: "Northfield Homes", short_forms: [], city: "Milton", province: "Ontario", dry_run: false,
  created_at: "2026-10-14T14:42:00Z", updated_at: "2026-10-14T14:50:00Z",
};

function serve({ toReview = 1, since = { value: "" } } = {}) {
  server.use(
    http.get(`${API}/admin/unbrander/summary`, ({ request }) => {
      since.value = new URL(request.url).searchParams.get("since") ?? "";
      return HttpResponse.json({ to_review: toReview, working: 2, jobs_since: 7, pages_cleaned_since: 386 });
    }),
    http.get(`${API}/admin/chat/summary`, () => HttpResponse.json({ active_users: 17, days: 30 })),
    http.get(`${API}/admin/unbrander/jobs`, ({ request }) =>
      HttpResponse.json({ jobs: new URL(request.url).searchParams.get("status") === "UNBRANDED" ? [READY] : [] })),
  );
}

test("Home shows what waits, what runs and this month's work, counted from Toronto's month", async () => {
  const since = { value: "" };
  serve({ since });
  renderApp("/");
  expect(await screen.findByText("386")).toBeInTheDocument();
  expect(screen.getByText("To review").nextElementSibling).toHaveTextContent("1");
  expect(screen.getByText("Working").nextElementSibling).toHaveTextContent("2");
  expect(since.value).toMatch(/^\d{4}-\d{2}-01T00:00:00-0[45]:00$/);
});

test("a job waiting for review is one link to its page", async () => {
  serve();
  const { user, router } = renderApp("/");
  const needsYou = await screen.findByRole("region", { name: "Needs you" });
  await user.click(await within(needsYou).findByRole("link", { name: /Bright Side Towns/ }));
  expect(router.state.location.pathname).toBe("/jobs/job-1");
});

test("the sidebar counts the jobs to review", async () => {
  serve({ toReview: 3 });
  renderApp("/");
  expect(await screen.findByRole("link", { name: "Unbranding, 3 to review" })).toBeInTheDocument();
});

test("the sidebar collapses and remembers it", async () => {
  serve();
  const { user } = renderApp("/");
  await user.click(await screen.findByRole("button", { name: "Collapse sidebar" }));
  expect(screen.getByRole("navigation", { name: "Main" })).toHaveAttribute("data-collapsed", "true");
  expect(localStorage.getItem("aura-agent.rail-collapsed")).toBe("1");
  await user.click(screen.getByRole("button", { name: "Expand sidebar" }));
  expect(localStorage.getItem("aura-agent.rail-collapsed")).toBe("0");
});

test("a failed count says so and offers a retry, and the rest of Home still shows", async () => {
  serve();
  server.use(http.get(`${API}/admin/unbrander/summary`, () =>
    HttpResponse.json({ detail: "database is down" }, { status: 503 })));
  renderApp("/");
  expect(await screen.findByRole("button", { name: "Try again" }, { timeout: 3000 })).toBeInTheDocument();
  expect(await screen.findByText("17")).toBeInTheDocument();
});

test("\"more\" counts every job waiting, not only the ones the list returned", async () => {
  serve({ toReview: 70 });
  renderApp("/");
  expect(await screen.findByRole("link", { name: "69 more" })).toHaveAttribute("href", "/jobs");
});
