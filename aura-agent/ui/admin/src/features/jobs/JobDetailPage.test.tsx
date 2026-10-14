import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { cleanedDocument, job } from "@/test/fixtures";
import { API } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderApp } from "@/test/render";

const JOB_URL = `${API}/admin/unbrander/jobs/job-1`;

function serve(body = job()) {
  server.use(http.get(JOB_URL, () => HttpResponse.json(body)));
}

const JPEG = () => new HttpResponse(new Uint8Array([0xff, 0xd8]), { headers: { "Content-Type": "image/jpeg" } });

test("a document opens full screen, before beside after, and the arrows turn its pages", async () => {
  const asked: string[] = [];
  server.use(http.get(`${JOB_URL}/documents/1/pages/:page`, ({ request, params }) => {
    asked.push(`${String(params.page)} ${new URL(request.url).searchParams.get("version")}`);
    return JPEG();
  }));
  serve();
  const { user, router } = renderApp("/jobs/job-1");
  await user.click(await screen.findByRole("link", { name: "Price list: compare before and after" }));
  const viewer = await screen.findByRole("dialog", { name: "Price list" });
  expect(await within(viewer).findByAltText("Page 1 as uploaded")).toBeInTheDocument();
  expect(await within(viewer).findByAltText("Page 1 after unbranding")).toBeInTheDocument();
  expect(within(viewer).getByText("Page 1 of 3")).toBeInTheDocument();
  // Names removed across the file belong to every page.
  expect(within(viewer).getByText(/Names removed: Arista/)).toBeInTheDocument();

  await user.click(within(viewer).getByRole("button", { name: "Next page" }));
  expect(within(viewer).getByText("Dropped")).toBeInTheDocument();
  expect(within(viewer).getByText("sales centre map")).toBeInTheDocument();
  expect(router.state.location.search).toBe("?doc=1&page=2");

  await user.keyboard("{ArrowRight}");
  expect(within(viewer).getByText("After · page 2")).toBeInTheDocument();
  expect(within(viewer).getByText("For review · Content lost")).toBeInTheDocument();
  expect(within(viewer).getByRole("button", { name: "Next page" })).toBeDisabled();
  expect(await within(viewer).findByAltText("Page 3 after unbranding")).toBeInTheDocument();
  expect(asked).toContain("3.jpg output");
  expect(asked).not.toContain("2.jpg output");
});

test("Escape closes the viewer and Back returns to the job, not through the pages", async () => {
  serve();
  const { user, router } = renderApp("/jobs/job-1");
  await user.click(await screen.findByRole("link", { name: "Price list: compare before and after" }));
  await screen.findByRole("dialog");
  await user.keyboard("{ArrowRight}");
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(router.state.location.search).toBe("");
  expect(router.state.location.pathname).toBe("/jobs/job-1");
});

test("a link to a page opens the viewer there, and closing it stays on the job", async () => {
  serve();
  const { user, router } = renderApp("/jobs/job-1?doc=1&page=3");
  const viewer = await screen.findByRole("dialog", { name: "Price list" });
  expect(within(viewer).getByText("Page 3 of 3")).toBeInTheDocument();
  await user.click(within(viewer).getByRole("button", { name: "Close" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/jobs/job-1");
});

test("a page image that fails can be retried", async () => {
  let failing = true;
  server.use(http.get(`${JOB_URL}/documents/1/pages/:page`, () => failing
    ? HttpResponse.json({ detail: "the file is not on the volume" }, { status: 404 })
    : JPEG()));
  serve(job({ documents: [cleanedDocument({ page_count: 1, page_map: { 1: 1 }, dropped_pages: [], findings: [] })] }));
  const { user } = renderApp("/jobs/job-1?doc=1&page=1");
  const before = await screen.findByRole("figure", { name: "Page 1, before" });
  const retry = await within(before).findByRole("button", { name: "Retry" });
  expect(within(before).getByText("the file is not on the volume")).toBeInTheDocument();
  failing = false;
  await user.click(retry);
  expect(await within(before).findByAltText("Page 1 as uploaded")).toBeInTheDocument();
});

test("a failed download says why", async () => {
  server.use(http.get(`${JOB_URL}/documents/1/output.pdf`, () =>
    HttpResponse.json({ detail: "the file is not on the volume" }, { status: 404 })));
  serve();
  const { user } = renderApp("/jobs/job-1?doc=1&page=1");
  await user.click(await screen.findByRole("button", { name: "Download cleaned PDF" }));
  expect(await screen.findByText("Download failed: the file is not on the volume")).toBeInTheDocument();
});

test("a download saves under the server's name", async () => {
  const saved: string[] = [];
  const click = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function save(this: HTMLAnchorElement) {
    saved.push(this.download);
  };
  server.use(http.get(`${JOB_URL}/documents/1/output.pdf`, () => new HttpResponse("%PDF-", {
    headers: { "Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="Price List.pdf"' },
  })));
  serve();
  const { user } = renderApp("/jobs/job-1");
  await user.click(await screen.findByRole("button", { name: "Download" }));
  await screen.findByRole("button", { name: "Download" });
  HTMLAnchorElement.prototype.click = click;
  expect(saved).toEqual(["Price List.pdf"]);
});

test("a document still waiting has no after and nothing to download", async () => {
  serve(job({ status: "UNBRANDING", ended_at: null,
    documents: [cleanedDocument({ status: "PENDING", page_count: 1, page_map: { 1: 1 }, findings: [], removed_items: [] })] }));
  renderApp("/jobs/job-1?doc=1&page=1");
  const viewer = await screen.findByRole("dialog");
  expect(within(viewer).getAllByText("Not cleaned yet").length).toBeGreaterThan(0);
  expect(within(viewer).queryByRole("button", { name: "Download cleaned PDF" })).not.toBeInTheDocument();
});

test("a document that failed says why, from the audit log", async () => {
  serve(job({
    status: "FAILED", error: "no document passed verification",
    documents: [cleanedDocument({ status: "FAILED", findings: [], removed_items: [] })],
    events: [{ job_id: "job-1", document_id: "doc-1", actor: "agent", action: "unbrand", result: "failed",
      detail: { reason: "took longer than 600 s" }, at: "2026-10-13T15:00:00Z" }],
  }));
  renderApp("/jobs/job-1");
  expect(await screen.findByText("Could not be unbranded: took longer than 600 s")).toBeInTheDocument();
  expect(screen.getByText("no document passed verification")).toBeInTheDocument();
});

test("a job that does not exist says so", async () => {
  server.use(http.get(JOB_URL, () => HttpResponse.json({ detail: "no such job" }, { status: 404 })));
  renderApp("/jobs/job-1");
  expect(await screen.findByText("no such job")).toBeInTheDocument();
});

test("an unbranded job can be filed in Drive from its page", async () => {
  let filed = false;
  server.use(
    http.get(JOB_URL, () => HttpResponse.json(job({ status: filed ? "FILING" : "UNBRANDED" }))),
    http.post(`${JOB_URL}/file`, () => {
      filed = true;
      return HttpResponse.json({ job_id: "job-1", status: "FILING" }, { status: 202 });
    }),
  );
  const { user } = renderApp("/jobs/job-1");
  await user.click(await screen.findByRole("button", { name: "File in Drive" }));
  expect(await screen.findByText(/Filing in Drive/)).toBeInTheDocument();
  expect(await screen.findByText("Filing")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "File in Drive" })).not.toBeInTheDocument();
});

test("filing without Drive set up says so, and the job stays a download", async () => {
  serve(job({ status: "UNBRANDED" }));
  server.use(http.post(`${JOB_URL}/file`, () => HttpResponse.json(
    { detail: "Drive is not set up on this service: download the cleaned PDFs instead" }, { status: 503 })));
  const { user } = renderApp("/jobs/job-1");
  await user.click(await screen.findByRole("button", { name: "File in Drive" }));
  expect(await screen.findByText(/Drive is not set up/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Download" })).toBeInTheDocument();
});

test("a job still unbranding has no File button", async () => {
  serve(job({ status: "UNBRANDING", ended_at: null }));
  renderApp("/jobs/job-1");
  await screen.findByRole("heading", { name: "SouthCal" });
  expect(screen.queryByRole("button", { name: "File in Drive" })).not.toBeInTheDocument();
});

test("the summary counts documents, changes and the final check, and each document opens its pages", async () => {
  serve(job({ status: "UNBRANDED" }));
  renderApp("/jobs/job-1");
  expect(await screen.findByText("Changes")).toBeInTheDocument();
  expect(screen.getByText("Changes").nextElementSibling).toHaveTextContent("2");
  expect(screen.getByText("Final check").nextElementSibling).toHaveTextContent("1/1");
  const documents = screen.getByRole("region", { name: "Documents" });
  expect(within(documents).getByRole("link", { name: "Price list: compare before and after" }))
    .toHaveAttribute("href", "/jobs/job-1?doc=1&page=1");
});

test("Download all keeps going past a failed document and names it", async () => {
  const saved: string[] = [];
  const click = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function save(this: HTMLAnchorElement) {
    saved.push(this.download);
  };
  server.use(
    http.get(`${JOB_URL}/documents/1/output.pdf`, () =>
      HttpResponse.json({ detail: "the file is not on the volume" }, { status: 404 })),
    http.get(`${JOB_URL}/documents/2/output.pdf`, () => new HttpResponse("%PDF-", {
      headers: { "Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="Floor Plan.pdf"' },
    })),
  );
  serve(job({ documents: [cleanedDocument(), cleanedDocument({ id: "doc-2", position: 2, doc_type: "floor_plan" })] }));
  const { user } = renderApp("/jobs/job-1");
  await user.click(await screen.findByRole("button", { name: "Download all" }));
  expect(await screen.findByText("Download failed: Price list not saved (the file is not on the volume)")).toBeInTheDocument();
  HTMLAnchorElement.prototype.click = click;
  expect(saved).toEqual(["Floor Plan.pdf"]);
});

test("a test job's page has no Test run label: test mode is shown on the list", async () => {
  serve(job({ dry_run: true }));
  renderApp("/jobs/job-1");
  await screen.findByRole("heading", { level: 1 });
  expect(screen.queryByText("Test run")).not.toBeInTheDocument();
});
