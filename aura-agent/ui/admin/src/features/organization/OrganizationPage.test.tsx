import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { job } from "@/test/fixtures";
import { API } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { serveOrganization } from "@/test/organization";
import { renderApp } from "@/test/render";

const saved = job().organization;

test("the profile is shown as facts, with its mark under Branding", async () => {
  serveOrganization();
  renderApp("/organization");
  expect(await screen.findByText("Aura Key Realty")).toBeInTheDocument();
  expect(screen.getByText("Name").nextElementSibling).toHaveTextContent("Aura Key Realty");
  expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Mark/ })).toHaveAttribute("href", "/organization/mark");
  expect(await screen.findByAltText("The mark as it will print on a page")).toBeInTheDocument();
});

test("Edit changes the details and sends the saved mark back unchanged", async () => {
  const { put } = serveOrganization();
  const { user } = renderApp("/organization");
  await user.click(await screen.findByRole("button", { name: "Edit" }));
  const save = screen.getByRole("button", { name: "Save" });
  expect(save).toBeDisabled();
  await user.clear(screen.getByLabelText("Region"));
  await user.type(screen.getByLabelText("Region"), "Toronto");
  await user.click(save);
  expect(await screen.findByText("Profile saved. Chat and new jobs use it now.")).toBeInTheDocument();
  expect(put[0]).toEqual({ ...saved, region: "Toronto" });
  expect(screen.queryByLabelText("Region")).not.toBeInTheDocument();
});

test("the server's field errors land on the fields", async () => {
  serveOrganization();
  server.use(http.put(`${API}/admin/organization`, () => HttpResponse.json({
    detail: [{ loc: ["body", "region"], msg: "String should have at most 80 characters" }],
  }, { status: 422 })));
  const { user } = renderApp("/organization");
  await user.click(await screen.findByRole("button", { name: "Edit" }));
  await user.type(screen.getByLabelText("Region"), "!");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("String should have at most 80 characters")).toBeInTheDocument();
});

test("a save the server cannot store says so", async () => {
  serveOrganization();
  server.use(http.put(`${API}/admin/organization`, () =>
    HttpResponse.json({ detail: "no database is configured" }, { status: 503 })));
  const { user } = renderApp("/organization");
  await user.click(await screen.findByRole("button", { name: "Edit" }));
  await user.type(screen.getByLabelText("Region"), "!");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("no database is configured");
});

test("leaving with unsaved changes asks first", async () => {
  serveOrganization();
  const { user, router } = renderApp("/organization");
  await user.click(await screen.findByRole("button", { name: "Edit" }));
  await user.type(screen.getByLabelText("Region"), "!");
  await user.click(screen.getByRole("link", { name: "Unbranding" }));
  expect(await screen.findByRole("alertdialog")).toHaveTextContent("Leave without saving?");
  await user.click(screen.getByRole("button", { name: "Stay" }));
  expect(router.state.location.pathname).toBe("/organization");
  await user.click(screen.getByRole("link", { name: "Unbranding" }));
  await user.click(await screen.findByRole("button", { name: "Leave" }));
  expect(await screen.findByRole("heading", { name: "Unbranding" })).toBeInTheDocument();
});
