import { screen } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";

import { job } from "@/test/fixtures";
import { API } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderApp } from "@/test/render";

const pdf = (name: string) => new File(["%PDF-1.7 test"], name, { type: "application/pdf" });

async function fillIn(user: ReturnType<typeof renderApp>["user"], files: File[]) {
  await user.type(await screen.findByLabelText("Project"), "SouthCal");
  await user.type(screen.getByLabelText("Builder"), "Arista Homes");
  await user.type(screen.getByLabelText("City"), "Vaughan");
  await user.upload(screen.getByLabelText("PDFs to unbrand"), files);
}

test("an upload sends the files and the facts, then opens the job", async () => {
  let sent: FormData | null = null;
  server.use(
    http.post(`${API}/admin/unbrander/jobs`, async ({ request }) => {
      sent = await request.formData();
      return HttpResponse.json({ job_id: "job-1", status: "RECEIVED" }, { status: 202 });
    }),
    http.get(`${API}/admin/unbrander/jobs/job-1`, () => HttpResponse.json(job())),
  );
  const { user, router } = renderApp("/jobs/new");
  await fillIn(user, [pdf("prices.pdf"), pdf("plans.pdf")]);
  await user.click(screen.getByRole("button", { name: "Upload and start" }));
  expect(await screen.findByRole("heading", { name: "SouthCal — Arista Homes" })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/jobs/job-1");
  const form = sent as unknown as FormData;
  expect(form.getAll("files").map((file) => (file as File).name)).toEqual(["prices.pdf", "plans.pdf"]);
  expect([form.get("project"), form.get("city"), form.get("province")]).toEqual(["SouthCal", "Vaughan", "Ontario"]);
  expect(form.get("file_when_done")).toBe("false");
});

test("File in Drive when done is sent when ticked", async () => {
  let sent: FormData | null = null;
  server.use(
    http.post(`${API}/admin/unbrander/jobs`, async ({ request }) => {
      sent = await request.formData();
      return HttpResponse.json({ job_id: "job-1", status: "RECEIVED" }, { status: 202 });
    }),
    http.get(`${API}/admin/unbrander/jobs/job-1`, () => HttpResponse.json(job())),
  );
  const { user } = renderApp("/jobs/new");
  await fillIn(user, [pdf("prices.pdf")]);
  await user.click(screen.getByRole("checkbox", { name: /File in Drive when done/ }));
  await user.click(screen.getByRole("button", { name: "Upload and start" }));
  await screen.findByRole("heading", { name: "SouthCal — Arista Homes" });
  expect((sent as unknown as FormData).get("file_when_done")).toBe("true");
});

test("a file that is not a PDF is refused before anything is sent", async () => {
  let posted = false;
  server.use(http.post(`${API}/admin/unbrander/jobs`, () => {
    posted = true;
    return HttpResponse.json({});
  }));
  const { user } = renderApp("/jobs/new");
  await fillIn(user, [pdf("prices.pdf"), new File(["PK\u0003\u0004"], "notes.pdf", { type: "application/pdf" })]);
  await user.click(screen.getByRole("button", { name: "Upload and start" }));
  expect(await screen.findByText("is not a PDF")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Remove or replace");
  expect(posted).toBe(false);
});

test("required facts are asked for before upload", async () => {
  const { user } = renderApp("/jobs/new");
  await user.click(await screen.findByRole("button", { name: "Upload and start" }));
  expect(await screen.findByText("Enter the project's name")).toBeInTheDocument();
  expect(screen.getByText("Enter the city")).toBeInTheDocument();
});

test("the server's refusal is shown against the upload", async () => {
  server.use(http.post(`${API}/admin/unbrander/jobs`, () =>
    HttpResponse.json({ detail: "plans.pdf: password-protected; upload an unlocked copy" }, { status: 422 })));
  const { user } = renderApp("/jobs/new");
  await fillIn(user, [pdf("plans.pdf")]);
  await user.click(screen.getByRole("button", { name: "Upload and start" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("plans.pdf: password-protected");
});

test("an upload can be cancelled and nothing is left half done", async () => {
  server.use(http.post(`${API}/admin/unbrander/jobs`, async () => {
    await delay("infinite");
    return HttpResponse.json({});
  }));
  const { user, router } = renderApp("/jobs/new");
  await fillIn(user, [pdf("prices.pdf")]);
  await user.click(screen.getByRole("button", { name: "Upload and start" }));
  await user.click(await screen.findByRole("button", { name: "Cancel upload" }));
  expect(await screen.findByRole("button", { name: "Upload and start" })).toBeEnabled();
  expect(router.state.location.pathname).toBe("/jobs/new");
});

test("the size limit is the server's, and a file over it is refused before upload", async () => {
  server.use(http.get(`${API}/admin/unbrander/limits`, () =>
    HttpResponse.json({ max_files: 10, max_file_mb: 1, max_pages: 60, can_file: true })));
  const { user } = renderApp("/jobs/new");
  expect(await screen.findByText("Up to 1 MB and 60 pages per file.")).toBeInTheDocument();
  const big = pdf("brochure.pdf");
  Object.defineProperty(big, "size", { value: 2 * 1024 ** 2 });
  await fillIn(user, [big]);
  await user.click(screen.getByRole("button", { name: "Upload and start" }));
  expect(await screen.findByText("is larger than 1 MB")).toBeInTheDocument();
});

test("auto-filing cannot be ticked when the service cannot file", async () => {
  server.use(http.get(`${API}/admin/unbrander/limits`, () =>
    HttpResponse.json({ max_files: 10, max_file_mb: 150, max_pages: 60, can_file: false })));
  renderApp("/jobs/new");
  expect(await screen.findByRole("checkbox", { name: /File in Drive when done/ })).toBeDisabled();
  expect(screen.getByText(/Not available: Drive is not set up/)).toBeInTheDocument();
});
