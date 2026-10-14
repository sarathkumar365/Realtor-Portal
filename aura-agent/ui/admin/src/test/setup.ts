import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";

import { endSession } from "@/features/auth/session";

import { server } from "./msw/server";

// jsdom has no object URLs; images and downloads only need a string back.
let objectUrls = 0;
URL.createObjectURL = () => `blob:test/${(objectUrls += 1)}`;
URL.revokeObjectURL = () => {};

// An unmocked call fails the test: tests never touch the network.
beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  endSession();
  sessionStorage.clear();
});
afterAll(() => server.close());
