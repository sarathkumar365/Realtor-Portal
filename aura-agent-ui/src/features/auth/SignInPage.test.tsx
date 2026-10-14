import { act, screen } from "@testing-library/react";

import { endSession, getSession } from "@/features/auth/session";
import { renderApp } from "@/test/render";

async function signInAs(user: ReturnType<typeof renderApp>["user"], id: string, password = "right") {
  await user.type(screen.getByLabelText("Portal ID"), id);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

test("an admin signs in and lands on Home", async () => {
  const { user, router } = renderApp("/sign-in", { signedIn: false });
  await signInAs(user, "admin");
  expect(await screen.findByRole("heading", { name: /^Good (morning|afternoon|evening)$/ })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/");
  expect(getSession()).toMatchObject({ user: "admin", name: "Sudhanshu" });
});

test("a realtor is refused and nothing is kept", async () => {
  const { user } = renderApp("/sign-in", { signedIn: false });
  await signInAs(user, "riya");
  expect(await screen.findByRole("alert")).toHaveTextContent("for admins");
  expect(getSession()).toBeNull();
  expect(sessionStorage.length).toBe(0);
});

test("a wrong password says so", async () => {
  const { user } = renderApp("/sign-in", { signedIn: false });
  await signInAs(user, "admin", "wrong");
  expect(await screen.findByRole("alert")).toHaveTextContent("Wrong portal ID or password.");
});

test("empty fields are caught before anything is sent", async () => {
  const { user } = renderApp("/sign-in", { signedIn: false });
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("Enter your portal ID")).toBeInTheDocument();
  expect(screen.getByText("Enter your password")).toBeInTheDocument();
});

test("a signed-out visitor is sent to sign-in and back to the page they asked for", async () => {
  const { user, router } = renderApp("/organization", { signedIn: false });
  expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  await signInAs(user, "admin");
  expect(await screen.findByRole("heading", { name: "Organization" })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/organization");
});

test("a session that ends mid-use goes to sign-in with the reason", async () => {
  renderApp("/jobs");
  expect(await screen.findByRole("heading", { name: "Unbranding" })).toBeInTheDocument();
  act(() => endSession("Your session ended. Sign in again."));
  expect(await screen.findByRole("status")).toHaveTextContent("Your session ended");
});

test("signing out ends the session", async () => {
  const { user } = renderApp("/jobs");
  await user.click(await screen.findByRole("button", { name: "Sign out" }));
  expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  expect(getSession()).toBeNull();
});
