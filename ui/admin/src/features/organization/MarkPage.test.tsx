import { screen, waitFor } from "@testing-library/react";

import { job } from "@/test/fixtures";
import { serveOrganization } from "@/test/organization";
import { renderApp } from "@/test/render";

const saved = job().organization;

test("a word is added and saved, and the page goes back to Organization", async () => {
  const { put } = serveOrganization();
  const { user, router } = renderApp("/settings/organization/mark");
  const save = await screen.findByRole("button", { name: "Save mark" });
  expect(save).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Add a word" }));
  await user.type(screen.getByLabelText("Word 2"), "KEY");
  await user.clear(screen.getByLabelText("Colour of word 2"));
  await user.type(screen.getByLabelText("Colour of word 2"), "#C9A227");
  await user.click(save);
  expect((await screen.findAllByText("Mark saved. New jobs use it now.")).length).toBeGreaterThan(0);
  expect(put[0]?.brand.mark_words).toEqual([{ text: "AURA", colour: "#0E1A24" }, { text: "KEY", colour: "#C9A227" }]);
  expect(put[0]?.name).toBe(saved.name);
  expect(router.state.location.pathname).toBe("/settings/organization");
});

test("a bad colour or word is caught before saving", async () => {
  const { put } = serveOrganization();
  const { user } = renderApp("/settings/organization/mark");
  await user.clear(await screen.findByLabelText("Colour of word 1"));
  await user.type(screen.getByLabelText("Colour of word 1"), "red");
  await user.type(screen.getByLabelText("Word 1"), " KEY");
  await user.click(screen.getByRole("button", { name: "Save mark" }));
  expect(await screen.findByText("A colour like #C9A227")).toBeInTheDocument();
  expect(screen.getByText("Letters only, one word")).toBeInTheDocument();
  expect(put).toEqual([]);
});

test("the preview follows a valid change without saving it, and skips an invalid one", async () => {
  const { previews, put } = serveOrganization();
  const { user } = renderApp("/settings/organization/mark");
  await screen.findByAltText("The mark as it will print on a page");
  const size = screen.getByLabelText("Size (pt)");
  await user.clear(size);
  await user.type(size, "12");
  await waitFor(() => expect(previews.at(-1)?.size).toBe(12), { timeout: 2000 });
  await user.clear(size);
  await new Promise((resolve) => setTimeout(resolve, 800));
  expect(previews.at(-1)?.size).toBe(12);
  expect(put).toEqual([]);
});

test("a size beyond the slider's range is kept as typed", async () => {
  const { put } = serveOrganization();
  const { user } = renderApp("/settings/organization/mark");
  const size = await screen.findByLabelText("Size (pt)");
  await user.clear(size);
  await user.type(size, "30");
  await user.click(screen.getByRole("button", { name: "Save mark" }));
  await waitFor(() => expect(put[0]?.brand.size).toBe(30));
});
