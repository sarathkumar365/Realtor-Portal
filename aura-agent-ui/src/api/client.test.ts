import { delay, http, HttpResponse } from "msw";

import { connectClient } from "@/app/connectClient";
import { getEndReason, getSession, startSession } from "@/features/auth/session";
import { API } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";

import { request } from "./client";
import { ApiError } from "./errors";

async function failure(call: Promise<unknown>): Promise<ApiError> {
  try {
    await call;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("the call succeeded");
}

beforeEach(() => {
  connectClient();
  startSession({ token: "admin-token", user: "admin", name: "Sudhanshu" });
});

test("a server that cannot be reached is offline, not a crash", async () => {
  server.use(http.get(`${API}/me`, () => HttpResponse.error()));
  expect((await failure(request("/me"))).kind).toBe("offline");
});

test("a slow answer times out with its own kind", async () => {
  server.use(http.get(`${API}/me`, async () => {
    await delay(200);
    return HttpResponse.json({});
  }));
  expect((await failure(request("/me", { timeoutMs: 20 }))).kind).toBe("timeout");
});

test("a 401 on a signed-in call ends the session and says why", async () => {
  server.use(http.get(`${API}/me`, () => HttpResponse.json({ detail: "token did not verify" }, { status: 401 })));
  expect((await failure(request("/me"))).kind).toBe("unauthorized");
  expect(getSession()).toBeNull();
  expect(getEndReason()).toMatch(/session ended/);
});

test("a 401 for a token being checked leaves the session alone", async () => {
  expect((await failure(request("/me", { token: "wrong" }))).kind).toBe("unauthorized");
  expect(getSession()).not.toBeNull();
});

test("validation errors are mapped to the fields they name", async () => {
  server.use(http.put(`${API}/admin/organization`, () => HttpResponse.json({
    detail: [{ loc: ["body", "brand", "mark_words", 0, "colour"], msg: "String should match pattern" }],
  }, { status: 422 })));
  const error = await failure(request("/admin/organization", { method: "PUT", json: {} }));
  expect(error.kind).toBe("invalid");
  expect(error.fields).toEqual({ "brand.mark_words.0.colour": "String should match pattern" });
});

test("a 403 is forbidden and a 5xx keeps the server's words", async () => {
  server.use(
    http.get(`${API}/me`, () => HttpResponse.json({ detail: "admin only" }, { status: 403 })),
    http.get(`${API}/health`, () => HttpResponse.json({ detail: "could not save the job" }, { status: 503 })),
  );
  expect((await failure(request("/me"))).kind).toBe("forbidden");
  const server5xx = await failure(request("/health"));
  expect([server5xx.kind, server5xx.message]).toEqual(["server", "could not save the job"]);
});
