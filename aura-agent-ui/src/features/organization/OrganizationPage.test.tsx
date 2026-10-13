import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { job } from "@/test/fixtures";
import { API, JPEG } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderApp } from "@/test/render";

const saved = job().organization;

function serve() {
  const put: unknown[] = [];
  const previews: unknown[] = [];
  server.use(
    http.get(`${API}/admin/organization`, () => HttpResponse.json(saved)),
    http.put(`${API}/admin/organization`, async ({ request }) => {
      const body = await request.json();
      put.push(body);
      return HttpResponse.json(body);
    }),
    http.post(`${API}/admin/unbrander/mark-preview`, async ({ request }) => {
      previews.push(await request.json());
      return new HttpResponse(JPEG, { headers: { "Content-Type": "image/jpeg" } });
    }),
  );
  return { put, previews };
}

test("the saved profile is shown with a preview of its mark", async () => {
  const { previews } = serve();
  renderApp("/organization");
  expect(await screen.findByLabelText("Name")).toHaveValue("Aura Key Realty");
  expect(screen.getByLabelText("Word 1")).toHaveValue("AURA");
  expect(await screen.findByAltText("The mark as it will print on a page")).toBeInTheDocument();
  expect(previews).toEqual([saved.brand]);
});

test("a change is saved, and Save is off until something changes", async () => {
  const { put } = serve();
  const { user } = renderApp("/organization");
  const save = await screen.findByRole("button", { name: "Save" });
  expect(save).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Add a word" }));
  await user.type(screen.getByLabelText("Word 2"), "KEY");
  await user.clear(screen.getByLabelText("Colour of word 2"));
  await user.type(screen.getByLabelText("Colour of word 2"), "#C9A227");
  await user.click(save);
  expect(await screen.findByText("Profile saved. Chat and new jobs use it now.")).toBeInTheDocument();
  expect((put[0] as typeof saved).brand.mark_words).toEqual([
    { text: "AURA", colour: "#0E1A24" }, { text: "KEY", colour: "#C9A227" }]);
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
});

test("a bad colour or word is caught before saving", async () => {
  const { put } = serve();
  const { user } = renderApp("/organization");
  await user.clear(await screen.findByLabelText("Colour of word 1"));
  await user.type(screen.getByLabelText("Colour of word 1"), "red");
  await user.type(screen.getByLabelText("Word 1"), " KEY");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("A colour like #C9A227")).toBeInTheDocument();
  expect(screen.getByText("Letters only, one word")).toBeInTheDocument();
  expect(put).toEqual([]);
});

test("the server's field errors land on the fields", async () => {
  serve();
  server.use(http.put(`${API}/admin/organization`, () => HttpResponse.json({
    detail: [{ loc: ["body", "brand", "opacity"], msg: "Input should be less than or equal to 1" }],
  }, { status: 422 })));
  const { user } = renderApp("/organization");
  await user.type(await screen.findByLabelText("Region"), "!");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Input should be less than or equal to 1")).toBeInTheDocument();
});

test("a save the server cannot store says so", async () => {
  serve();
  server.use(http.put(`${API}/admin/organization`, () =>
    HttpResponse.json({ detail: "no database is configured" }, { status: 503 })));
  const { user } = renderApp("/organization");
  await user.type(await screen.findByLabelText("Region"), "!");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("no database is configured");
});

test("Preview draws the edited mark before it is saved", async () => {
  const { previews, put } = serve();
  const { user } = renderApp("/organization");
  const size = await screen.findByLabelText("Size (pt)");
  await user.clear(size);
  await user.type(size, "12");
  await user.click(screen.getByRole("button", { name: "Preview changes" }));
  await screen.findByAltText("The mark as it will print on a page");
  expect((previews.at(-1) as typeof saved.brand).size).toBe(12);
  expect(put).toEqual([]);
});

test("leaving with unsaved changes asks first", async () => {
  serve();
  const { user, router } = renderApp("/organization");
  await user.type(await screen.findByLabelText("Region"), "!");
  await user.click(screen.getByRole("link", { name: "Unbrander jobs" }));
  expect(await screen.findByRole("alertdialog")).toHaveTextContent("Leave without saving?");
  await user.click(screen.getByRole("button", { name: "Stay" }));
  expect(router.state.location.pathname).toBe("/organization");
  await user.click(screen.getByRole("link", { name: "Unbrander jobs" }));
  await user.click(await screen.findByRole("button", { name: "Leave" }));
  expect(await screen.findByRole("heading", { name: "Unbrander jobs" })).toBeInTheDocument();
});
