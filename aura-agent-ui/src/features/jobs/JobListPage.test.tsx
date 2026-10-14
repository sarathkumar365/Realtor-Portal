import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { cleanedDocument, job, jobSummary } from "@/test/fixtures";
import { API } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderApp } from "@/test/render";

/** The list as the server answers it: filtered by the repeated `status`, with
 * each job's documents when `documents=true`. */
function serve(jobs: ReturnType<typeof jobSummary>[], documents: Record<string, ReturnType<typeof job>["documents"]> = {}) {
  const asked: string[] = [];
  server.use(http.get(`${API}/admin/unbrander/jobs`, ({ request }) => {
    const url = new URL(request.url);
    const statuses = url.searchParams.getAll("status");
    asked.push(statuses.join(","));
    const listed = jobs.filter((one) => statuses.length === 0 || statuses.includes(one.status));
    return HttpResponse.json({
      jobs: listed,
      documents: url.searchParams.get("documents") === "true"
        ? Object.fromEntries(listed.map((one) => [one.id, documents[one.id] ?? []])) : null,
    });
  }));
  return asked;
}

test("jobs fall into review, working and done, each one link to its job", async () => {
  serve([
    jobSummary({ id: "ready", project: "SouthCal", status: "UNBRANDED" }),
    jobSummary({ id: "busy", project: "Kleinburg", status: "UNBRANDING", ended_at: null }),
    jobSummary({ id: "filed", project: "Union Village", status: "FILED_PRIVATE" }),
    jobSummary({ id: "broken", project: "Northshore", status: "FAILED" }),
  ], {
    ready: [cleanedDocument()],
    busy: [cleanedDocument({ status: "UNBRANDING" }), cleanedDocument({ id: "doc-2", position: 2, status: "PENDING" })],
  });
  renderApp("/jobs");
  const review = await screen.findByRole("region", { name: "Needs your review" });
  expect(within(review).getByRole("link", { name: /SouthCal/ })).toHaveAttribute("href", "/jobs/ready");
  // The fixture document removed two items: a dropped page and the builder's name.
  expect(await within(review).findByText("2 changes")).toBeInTheDocument();
  const working = screen.getByRole("region", { name: "Working" });
  expect(await within(working).findByText(/Document 1 of 2 · Price list/)).toBeInTheDocument();
  const done = screen.getByRole("region", { name: "Done" });
  expect(within(done).getByRole("link", { name: /Union Village/ })).toHaveTextContent("Filed in Drive");
  expect(within(done).getByRole("link", { name: /Northshore/ })).toHaveTextContent("Failed");
});

test("a job open for more than a day is flagged as possibly stuck", async () => {
  serve([jobSummary({ status: "RECEIVED", created_at: "2020-01-01T00:00:00Z", ended_at: null })]);
  renderApp("/jobs");
  expect(await screen.findByText("Stuck?")).toBeInTheDocument();
});

test("with no jobs the page says so and offers an upload", async () => {
  serve([]);
  renderApp("/jobs");
  expect(await screen.findByText("No jobs yet")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Upload PDFs" })).toHaveAttribute("href", "/jobs/new");
});

test("each section is asked for by its own statuses, so none crowds out another", async () => {
  const asked = serve([]);
  renderApp("/jobs");
  await screen.findByText("No jobs yet");
  expect(asked.sort()).toEqual(["FILED_PRIVATE,FAILED", "RECEIVED,UNBRANDING,FILING", "UNBRANDED"]);
});

test("a list that cannot load says why and retries", async () => {
  let down = true;
  server.use(http.get(`${API}/admin/unbrander/jobs`, () =>
    down ? HttpResponse.error() : HttpResponse.json({ jobs: [], documents: null })));
  const { user } = renderApp("/jobs");
  expect(await screen.findByText(/Cannot reach Aura/, {}, { timeout: 3000 })).toBeInTheDocument();
  down = false;
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("No jobs yet")).toBeInTheDocument();
});
