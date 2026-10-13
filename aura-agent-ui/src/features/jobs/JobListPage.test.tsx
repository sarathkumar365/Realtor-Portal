import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { job, jobSummary } from "@/test/fixtures";
import { API } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderApp } from "@/test/render";

test("jobs are listed newest first with their status and a link", async () => {
  server.use(http.get(`${API}/admin/unbrander/jobs`, () => HttpResponse.json({
    jobs: [jobSummary(), jobSummary({ id: "job-2", project: "Kleinburg", status: "FAILED" })],
  })));
  renderApp("/jobs");
  const rows = await screen.findAllByRole("row");
  expect(within(rows[1]!).getByRole("link", { name: "SouthCal" })).toHaveAttribute("href", "/jobs/job-1");
  expect(within(rows[2]!).getByText("Failed")).toBeInTheDocument();
});

test("a job open for more than a day is flagged as possibly stuck", async () => {
  server.use(http.get(`${API}/admin/unbrander/jobs`, () => HttpResponse.json({
    jobs: [jobSummary({ status: "RECEIVED", created_at: "2020-01-01T00:00:00Z", ended_at: null })],
  })));
  renderApp("/jobs");
  expect(await screen.findByText("Stuck?")).toBeInTheDocument();
});

test("the filter asks the server for one status", async () => {
  const asked: (string | null)[] = [];
  server.use(http.get(`${API}/admin/unbrander/jobs`, ({ request }) => {
    asked.push(new URL(request.url).searchParams.get("status"));
    return HttpResponse.json({ jobs: [] });
  }));
  const { user } = renderApp("/jobs");
  await screen.findByText("No jobs yet");
  await user.click(screen.getByRole("tab", { name: "Failed" }));
  expect(await screen.findByText("No jobs with this status")).toBeInTheDocument();
  expect(asked).toEqual([null, "FAILED"]);
});

test("a list that cannot load says why and retries", async () => {
  let calls = 0;
  server.use(http.get(`${API}/admin/unbrander/jobs`, () => {
    calls += 1;
    return calls <= 3 ? HttpResponse.error() : HttpResponse.json({ jobs: [] });
  }));
  const { user } = renderApp("/jobs");
  expect(await screen.findByText(/Cannot reach Aura/, {}, { timeout: 3000 })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("No jobs yet")).toBeInTheDocument();
});

test("clicking anywhere on a row opens the job", async () => {
  server.use(
    http.get(`${API}/admin/unbrander/jobs`, () => HttpResponse.json({ jobs: [jobSummary()] })),
    http.get(`${API}/admin/unbrander/jobs/job-1`, () => HttpResponse.json(job())),
  );
  const { user, router } = renderApp("/jobs");
  const link = await screen.findByRole("link", { name: "SouthCal" });
  // jsdom has no layout, so the stretch itself is checked in a browser; here, that
  // the link carries it and the row is its containing block.
  expect(link.className).toContain("after:inset-0");
  expect(link.closest("tr")?.className).toContain("relative");
  await user.click(link);
  expect(router.state.location.pathname).toBe("/jobs/job-1");
});
