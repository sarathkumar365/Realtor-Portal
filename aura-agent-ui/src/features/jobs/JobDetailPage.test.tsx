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

test("pages pair by source page; a dropped page says why, findings sit on their page", async () => {
  const asked: string[] = [];
  server.use(http.get(`${JOB_URL}/documents/1/pages/:page`, ({ request, params }) => {
    asked.push(`${String(params.page)} ${new URL(request.url).searchParams.get("version")}`);
    return new HttpResponse(new Uint8Array([0xff, 0xd8]), { headers: { "Content-Type": "image/jpeg" } });
  }));
  serve();
  renderApp("/jobs/job-1");
  const page2 = await screen.findByRole("region", { name: "Page 2" });
  expect(within(page2).getByText("sales centre map")).toBeInTheDocument();
  const page3 = screen.getByRole("region", { name: "Page 3" });
  expect(within(page3).getByText("Content lost")).toBeInTheDocument();
  expect(within(page3).getByText("After · page 2")).toBeInTheDocument();
  expect(await within(page3).findByAltText("Page 3 after unbranding")).toBeInTheDocument();
  expect(asked.sort()).toEqual(["1.jpg output", "1.jpg source", "2.jpg source", "3.jpg output", "3.jpg source"]);
});

test("what was removed is listed, without the dropped pages", async () => {
  serve();
  renderApp("/jobs/job-1");
  expect(await screen.findByText("Names removed: Arista")).toBeInTheDocument();
  expect(screen.queryByText("Page 2 dropped")).not.toBeInTheDocument();
});

test("a page image that fails can be retried", async () => {
  let failing = true;
  server.use(http.get(`${JOB_URL}/documents/1/pages/:page`, () => failing
    ? HttpResponse.json({ detail: "the file is not on the volume" }, { status: 404 })
    : new HttpResponse(new Uint8Array([0xff, 0xd8]), { headers: { "Content-Type": "image/jpeg" } })));
  serve(job({ documents: [cleanedDocument({ page_count: 1, page_map: { 1: 1 }, dropped_pages: [], findings: [] })] }));
  const { user } = renderApp("/jobs/job-1");
  const page = await screen.findByRole("region", { name: "Page 1" });
  const retries = await within(page).findAllByRole("button", { name: "Retry" });
  expect(within(page).getAllByText("the file is not on the volume")).toHaveLength(2);
  failing = false;
  await user.click(retries[0]!);
  expect(await within(page).findByAltText("Page 1 as uploaded")).toBeInTheDocument();
});

test("a failed download says why", async () => {
  server.use(http.get(`${JOB_URL}/documents/1/output.pdf`, () =>
    HttpResponse.json({ detail: "the file is not on the volume" }, { status: 404 })));
  serve();
  const { user } = renderApp("/jobs/job-1");
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
  await user.click(await screen.findByRole("button", { name: "Download cleaned PDF" }));
  await screen.findByRole("button", { name: "Download cleaned PDF" });
  HTMLAnchorElement.prototype.click = click;
  expect(saved).toEqual(["Price List.pdf"]);
});

test("a document still waiting shows its pages without an after", async () => {
  serve(job({ status: "UNBRANDING", ended_at: null,
    documents: [cleanedDocument({ status: "PENDING", page_count: 1, page_map: { 1: 1 }, findings: [], removed_items: [] })] }));
  renderApp("/jobs/job-1");
  expect(await screen.findByText("Not cleaned yet")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Download cleaned PDF" })).not.toBeInTheDocument();
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
  expect(screen.getByRole("button", { name: "Download cleaned PDF" })).toBeInTheDocument();
});

test("a job still unbranding has no File button", async () => {
  serve(job({ status: "UNBRANDING", ended_at: null }));
  renderApp("/jobs/job-1");
  await screen.findByRole("heading", { name: "SouthCal — Arista Homes" });
  expect(screen.queryByRole("button", { name: "File in Drive" })).not.toBeInTheDocument();
});
