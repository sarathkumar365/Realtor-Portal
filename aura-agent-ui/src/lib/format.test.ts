import { greeting, startOfMonth } from "./format";

test("the month starts at Toronto midnight, in daylight time and out of it", () => {
  expect(startOfMonth(new Date("2026-10-14T15:00:00Z"))).toBe("2026-10-01T00:00:00-04:00");
  expect(startOfMonth(new Date("2026-12-31T12:00:00Z"))).toBe("2026-12-01T00:00:00-05:00");
  // 02:00 UTC on Nov 1 is still Oct 31 in Toronto.
  expect(startOfMonth(new Date("2026-11-01T02:00:00Z"))).toBe("2026-10-01T00:00:00-04:00");
});

test("the greeting follows the hour in Toronto, not the browser's", () => {
  expect(greeting(new Date("2026-10-14T13:00:00Z"))).toBe("Good morning");
  expect(greeting(new Date("2026-10-14T20:00:00Z"))).toBe("Good afternoon");
  expect(greeting(new Date("2026-10-15T01:00:00Z"))).toBe("Good evening");
});
