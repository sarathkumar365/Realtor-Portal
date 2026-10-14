import type { Job, JobDocument, JobSummary } from "@/api/jobs";

const NOW = "2026-10-13T15:00:00Z";

export function jobSummary(overrides: Partial<JobSummary> = {}): JobSummary {
  return {
    id: "job-1", status: "FILED_PRIVATE", uploader: "admin", instructions: null, project: "SouthCal",
    builder: "Arista Homes", short_forms: [], city: "Vaughan", province: "Ontario", dry_run: true,
    file_when_done: false,
    created_at: NOW, updated_at: NOW, ended_at: NOW, ...overrides,
  };
}

/** A price list of 3 pages, page 2 dropped, a finding on page 3. */
export function cleanedDocument(overrides: Partial<JobDocument> = {}): JobDocument {
  return {
    id: "doc-1", job_id: "job-1", position: 1, filename: "Arista_SouthCal_Pricelist.pdf", sha256: "",
    page_count: 3, status: "VERIFIED", doc_type: "price_list", dropped_pages: [2],
    page_map: { 1: 1, 2: null, 3: 2 },
    findings: [{ check: "damage", severity: "flag", detail: "words gone from source page 3: Lot", page: 3 }],
    removed_items: [
      { ok: true, detail: "", action: { tool: "drop_page", page: 2, why: "sales centre map" } },
      { ok: true, detail: "", action: { tool: "redact_terms", terms: ["Arista"], why: "the builder's name" } },
    ],
    rounds: 1, usage: {}, cost_usd: 0.042, drive_file_id: null, started_at: NOW,
    ...overrides,
  };
}

export function job(overrides: Partial<Job> = {}): Job {
  return {
    ...jobSummary(),
    organization: { name: "Aura Key Realty", short_name: "Aura Key", assistant_name: "Aura",
      region: "the Greater Toronto Area", brand: { mark_words: [{ text: "AURA", colour: "#0E1A24" }],
        font: "Times", size: 7.5, tracking: 1.6, opacity: 0.55, margin: 36 } },
    documents: [cleanedDocument()],
    events: [{ job_id: "job-1", actor: "admin", action: "upload", result: "accepted", detail: {}, at: NOW }],
    ...overrides,
  } as Job;
}
