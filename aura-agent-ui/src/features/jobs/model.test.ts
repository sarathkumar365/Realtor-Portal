import type { JobDocument } from "@/api/jobs";

import { isStale, pairPages, removals, wholeFileFindings } from "./model";

const document: JobDocument = {
  id: "d1", job_id: "j1", position: 1, filename: "prices.pdf", sha256: "", page_count: 3, status: "VERIFIED",
  dropped_pages: [2],
  page_map: { 1: 1, 2: null, 3: 2 },
  findings: [
    { check: "damage", severity: "flag", detail: "words gone", page: 3 },
    { check: "metadata", severity: "flag", detail: "producer", page: null },
  ],
  removed_items: [
    { ok: true, detail: "", action: { tool: "drop_page", page: 2, why: "sales centre map" } },
    { ok: true, detail: "", action: { tool: "redact_terms", terms: ["Arista"], why: "builder" } },
  ],
};

test("pages pair by source number, and a dropped page says why", () => {
  expect(pairPages(document).map(({ source, output, droppedBecause, findings }) =>
    [source, output, droppedBecause, findings.length])).toEqual([
    [1, 1, null, 0],
    [2, null, "sales centre map", 0],
    [3, 2, null, 1],
  ]);
});

test("whole-file findings and removals are listed apart from the pages", () => {
  expect(wholeFileFindings(document).map((finding) => finding.check)).toEqual(["metadata"]);
  expect(removals(document).map((item) => item.action.tool)).toEqual(["redact_terms"]);
});

test("an open job older than a day is stale; an ended one never is", () => {
  const now = Date.parse("2026-10-13T12:00:00Z");
  expect(isStale("RECEIVED", "2026-10-12T11:00:00Z", now)).toBe(true);
  expect(isStale("RECEIVED", "2026-10-13T11:00:00Z", now)).toBe(false);
  expect(isStale("FAILED", "2026-10-01T11:00:00Z", now)).toBe(false);
});
