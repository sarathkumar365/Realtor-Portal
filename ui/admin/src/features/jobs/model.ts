import { type DocumentStatus, ENDED, type Finding, type JobDocument, type JobStatus, type Outcome } from "@/api/jobs";
import type { StatusKind } from "@/components/StatusMark";
import type { BadgeTone } from "@/components/ui/badge";

// A state is a glyph and a word (DESIGN.md). Gold, "review", is only for a job
// cleaned and waiting for an admin.
export const JOB_STATUS: Record<JobStatus, { label: string; kind: StatusKind }> = {
  RECEIVED: { label: "Waiting", kind: "idle" },
  UNBRANDING: { label: "Working", kind: "working" },
  UNBRANDED: { label: "Needs review", kind: "review" },
  FILING: { label: "Filing", kind: "working" },
  FILED_PRIVATE: { label: "Filed in Drive", kind: "done" },
  FAILED: { label: "Failed", kind: "failed" },
};

export const DOCUMENT_STATUS: Record<DocumentStatus, { label: string; kind: StatusKind }> = {
  PENDING: { label: "Waiting", kind: "idle" },
  UNBRANDING: { label: "Working", kind: "working" },
  VERIFIED: { label: "Passed", kind: "done" },
  BLOCKED: { label: "Blocked", kind: "failed" },
  FILED: { label: "Filed", kind: "done" },
  FAILED: { label: "Failed", kind: "failed" },
};

export const SEVERITY: Record<Finding["severity"], { label: string; tone: BadgeTone }> = {
  block: { label: "Blocks", tone: "danger" },
  retry: { label: "Retried", tone: "warning" },
  flag: { label: "For review", tone: "info" },
};

export const CHECK: Record<Finding["check"], string> = {
  text_sweep: "Name left in text",
  raw_bytes: "Name left in the file",
  ocr_sweep: "Name visible in image",
  numbers: "Number changed",
  provenance: "New text appeared",
  metadata: "Metadata",
  cover_up: "Possible cover-up",
  pages: "Pages",
  damage: "Content lost",
  visual: "Seen by the judge",
};

export const DOC_TYPE: Record<string, string> = {
  price_list: "Price list", floor_plan: "Floor plan", site_plan: "Site plan", feature_sheet: "Features",
  terms: "Terms", elevation: "Elevations", marketing: "Marketing",
};

/** A job open this long is probably stuck: the worker is off, or over its daily cap. */
export const STALE_AFTER_MS = 24 * 60 * 60 * 1000;

export function isStale(status: JobStatus, createdAt: string, now = Date.now()): boolean {
  return !ENDED.has(status) && now - Date.parse(createdAt) > STALE_AFTER_MS;
}

/** The document has a cleaned file to look at. */
export function hasOutput(document: JobDocument): boolean {
  return document.status === "VERIFIED" || document.status === "BLOCKED" || document.status === "FILED";
}

export interface PagePairing {
  source: number;
  /** The output page made from it, or null when it was dropped. */
  output: number | null;
  findings: Finding[];
  droppedBecause: string | null;
}

/** Each source page with its output page and the findings on it. Findings are in
 * source page numbers (the server converts verify()'s), so they pair directly. */
export function pairPages(document: JobDocument): PagePairing[] {
  const pages = [];
  for (let page = 1; page <= document.page_count; page += 1) {
    const output = document.page_map[String(page)] ?? null;
    pages.push({
      source: page,
      output,
      findings: (document.findings ?? []).filter((finding) => finding.page === page),
      droppedBecause: output === null ? dropReason(document.removed_items ?? [], page) : null,
    });
  }
  return pages;
}

function dropReason(removed: Outcome[], page: number): string {
  const drop = removed.find((item) => item.action.tool === "drop_page" && "page" in item.action && item.action.page === page);
  return drop?.action.why ?? "dropped";
}

/** Findings about the whole file (metadata, raw bytes), not one page. */
export function wholeFileFindings(document: JobDocument): Finding[] {
  return (document.findings ?? []).filter((finding) => finding.page == null);
}

/** What was removed, without the dropped pages: those show beside their page. */
export function removals(document: JobDocument): Outcome[] {
  return (document.removed_items ?? []).filter((item) => item.action.tool !== "drop_page");
}

/** A removal as the viewer lists it beside its page, so without the page number. */
export function removalKind(item: Outcome): string {
  switch (item.action.tool) {
    case "redact_rect":
      return "Area cleared";
    case "remove_element":
      return "Element removed";
    case "drop_page":
      return "Page dropped";
    default:
      return describeRemoval(item);
  }
}

export function describeRemoval(item: Outcome): string {
  const action = item.action;
  switch (action.tool) {
    case "redact_terms":
      return `Names removed: ${action.terms.join(", ")}`;
    case "redact_rect":
      return `Area cleared on page ${action.page}`;
    case "remove_element":
      return `Element ${action.element_id} removed on page ${action.page}`;
    case "drop_page":
      return `Page ${action.page} dropped`;
    case "add_mark":
      return "Mark added";
  }
}

/** What a document is called on screen: its sorted type, or its place in the upload. */
export function documentName(document: JobDocument): string {
  return document.doc_type ? (DOC_TYPE[document.doc_type] ?? document.doc_type) : `Document ${document.position}`;
}

/** Everything the agent changed in a document, dropped pages included. */
export function changeCount(document: JobDocument): number {
  return (document.removed_items ?? []).length;
}

/** Changes per source page. Names removed across the file (redact_terms) belong
 * to no page, so they are not here. */
export function changesByPage(document: JobDocument): Map<number, number> {
  const pages = new Map<number, number>();
  for (const item of document.removed_items ?? []) {
    if ("page" in item.action && typeof item.action.page === "number") {
      pages.set(item.action.page, (pages.get(item.action.page) ?? 0) + 1);
    }
  }
  return pages;
}

/** The first source page that survived, to stand for the document; 1 if none did. */
export function firstKeptPage(document: JobDocument): number {
  for (let page = 1; page <= document.page_count; page += 1) {
    if (document.page_map[String(page)] != null) return page;
  }
  return 1;
}

export function keptPages(document: JobDocument): number {
  return document.page_count - (document.dropped_pages?.length ?? 0);
}

export interface Progress {
  stage: "Waiting" | "Unbranding" | "Filing";
  done: number;
  total: number;
  /** The document being unbranded now, as "Document 2 of 3 · Price list". */
  current: string | null;
}

/** How far an open job has got, from its documents' statuses: the worker reports
 * no finer progress than that. */
export function progress(job: { status: JobStatus; documents?: JobDocument[] }): Progress {
  const documents = job.documents ?? [];
  const total = documents.length;
  if (job.status === "FILING") {
    return { stage: "Filing", done: documents.filter((document) => document.status === "FILED").length, total, current: null };
  }
  const done = documents.filter((document) => document.status !== "PENDING" && document.status !== "UNBRANDING").length;
  const working = documents.find((document) => document.status === "UNBRANDING");
  if (job.status === "RECEIVED" && !working) return { stage: "Waiting", done, total, current: null };
  return {
    stage: "Unbranding", done, total,
    current: working ? `Document ${working.position} of ${total} · ${documentName(working)}` : null,
  };
}

/** Documents that came through the final check clean. */
export function passedCount(documents: JobDocument[]): number {
  return documents.filter((document) => document.status === "VERIFIED" || document.status === "FILED").length;
}
